from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .session import DISCOVERY_MAGIC, DISCOVERY_PORT, DEFAULT_PORT, LanGameFinder


LAN_LOBBY_PORT = DEFAULT_PORT + 5
LAN_LOBBY_MAGIC = "grid_survival_lobby_v1"


@dataclass(slots=True)
class LobbyMember:
    name: str
    address: tuple[str, int]
    character: str = "Caveman"
    ready: bool = False
    is_host: bool = False
    joined_at: float = field(default_factory=time.time)

    def to_message(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "character": self.character,
            "ready": bool(self.ready),
            "is_host": bool(self.is_host),
        }


class LanLobbyHostSession:
    """Best-effort LAN lobby control plane that can track multiple members.

    This does not replace the match transport. It coordinates pre-match state:
    join order, roster, character picks, and the final host configuration.
    """

    def __init__(self, *, host_name: str, max_players: int, port: int = LAN_LOBBY_PORT):
        self.host_name = str(host_name or "Host")
        self.max_players = max(2, min(4, int(max_players)))
        self.port = int(port)
        self.socket: Optional[socket.socket] = None
        self.discovery_socket: Optional[socket.socket] = None
        self.discovery_thread: Optional[threading.Thread] = None
        self.discovery_running = False
        self.running = False
        self.last_error: Optional[str] = None
        self.members: dict[tuple[str, int], LobbyMember] = {}
        self.members[("host", self.port)] = LobbyMember(
            name=self.host_name,
            address=("127.0.0.1", self.port),
            is_host=True,
            ready=True,
        )
        self.host_config: dict[str, Any] = {}
        self.finalized = False

    def start(self) -> bool:
        try:
            lobby_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            lobby_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            lobby_socket.bind(("0.0.0.0", self.port))
            lobby_socket.settimeout(0.05)
            self.socket = lobby_socket
            self.running = True
            self._start_discovery_responder()
            return True
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            self.close()
            return False

    def close(self) -> None:
        self.running = False
        self.finalized = True
        self._stop_discovery_responder()
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None

    def set_host_config(self, **config: Any) -> None:
        self.host_config = dict(config)
        self.broadcast_state(final=False)

    def set_member_character(self, address: tuple[str, int], character: str) -> None:
        member = self.members.get(address)
        if member is None:
            return
        member.character = str(character or member.character)
        self.broadcast_state(final=False)

    def set_member_ready(self, address: tuple[str, int], ready: bool) -> None:
        member = self.members.get(address)
        if member is None:
            return
        member.ready = bool(ready)
        self.broadcast_state(final=False)

    def poll(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if not self.socket:
            return messages

        while True:
            try:
                payload, address = self.socket.recvfrom(4096)
            except socket.timeout:
                break
            except (socket.error, OSError):
                self.last_error = self.last_error or "Lobby socket closed"
                break

            try:
                message = json.loads(payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(message, dict):
                continue
            if message.get("magic") != LAN_LOBBY_MAGIC:
                continue

            msg_type = str(message.get("type", ""))
            if msg_type == "join":
                self._handle_join(address, message)
                messages.append({"type": "join", "address": address, **message})
            elif msg_type == "leave":
                self.members.pop(address, None)
                self.broadcast_state(final=False)
                messages.append({"type": "leave", "address": address, **message})
            elif msg_type == "ready":
                self.set_member_ready(address, bool(message.get("ready", True)))
                messages.append({"type": "ready", "address": address, **message})
            elif msg_type == "character":
                self.set_member_character(address, str(message.get("character", "Caveman")))
                messages.append({"type": "character", "address": address, **message})
            elif msg_type == "host_config":
                self.host_config.update({k: v for k, v in message.items() if k not in {"magic", "type"}})
                self.broadcast_state(final=False)
                messages.append({"type": "host_config", "address": address, **message})
        return messages

    def wait_for_member_count(self, target_count: int, *, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.time() + max(0.0, float(timeout))
        while self.running:
            self.poll()
            if len(self.members) >= max(2, min(self.max_players, int(target_count))):
                return True
            self.broadcast_state(final=False)
            if deadline is not None and time.time() >= deadline:
                return False
            time.sleep(0.05)
        return False

    def all_ready(self) -> bool:
        return len(self.members) >= 2 and all(member.ready for member in self.members.values())

    def roster(self) -> list[LobbyMember]:
        return sorted(self.members.values(), key=lambda member: (not member.is_host, member.joined_at))

    def roster_payload(self) -> list[dict[str, Any]]:
        return [member.to_message() for member in self.roster()]

    def broadcast_state(self, *, final: bool = False) -> None:
        if not self.socket:
            return
        payload = {
            "magic": LAN_LOBBY_MAGIC,
            "type": "lobby_state",
            "host_name": self.host_name,
            "member_count": len(self.members),
            "max_players": self.max_players,
            "members": self.roster_payload(),
            "host_config": dict(self.host_config),
            "final": bool(final),
        }
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        for member in list(self.members.values()):
            if member.is_host:
                continue
            try:
                self.socket.sendto(encoded, member.address)
            except (socket.error, OSError):
                continue
        try:
            self.socket.sendto(encoded, ("255.255.255.255", self.port))
        except (socket.error, OSError):
            pass

    def finalize(self) -> dict[str, Any]:
        self.finalized = True
        state = {
            "host_name": self.host_name,
            "max_players": self.max_players,
            "members": self.roster_payload(),
            "host_config": dict(self.host_config),
        }
        self.broadcast_state(final=True)
        return state

    def _handle_join(self, address: tuple[str, int], message: dict[str, Any]) -> None:
        if address not in self.members and len(self.members) >= self.max_players:
            self._send_join_reject(address, reason="Lobby full")
            return

        name = str(message.get("name", f"Player {len(self.members) + 1}"))
        character = str(message.get("character", "Caveman"))
        member = self.members.get(address)
        if member is None:
            member = LobbyMember(name=name, address=address, character=character, is_host=False)
            self.members[address] = member
        else:
            member.name = name
            member.character = character

        self._send_join_ack(address)
        self.broadcast_state(final=False)

    def _send_join_ack(self, address: tuple[str, int]) -> None:
        if not self.socket:
            return
        ack = {
            "magic": LAN_LOBBY_MAGIC,
            "type": "join_ack",
            "host_name": self.host_name,
            "max_players": self.max_players,
            "members": self.roster_payload(),
            "host_config": dict(self.host_config),
        }
        try:
            self.socket.sendto(json.dumps(ack, separators=(",", ":")).encode("utf-8"), address)
        except (socket.error, OSError):
            pass

    def _send_join_reject(self, address: tuple[str, int], *, reason: str) -> None:
        if not self.socket:
            return
        msg = {
            "magic": LAN_LOBBY_MAGIC,
            "type": "join_reject",
            "reason": str(reason),
            "max_players": self.max_players,
        }
        try:
            self.socket.sendto(json.dumps(msg, separators=(",", ":")).encode("utf-8"), address)
        except (socket.error, OSError):
            pass

    def _start_discovery_responder(self) -> None:
        discovery = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        discovery.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        discovery.bind(("0.0.0.0", DISCOVERY_PORT))
        discovery.settimeout(0.25)
        self.discovery_socket = discovery
        self.discovery_running = True
        self.discovery_thread = threading.Thread(target=self._discovery_loop, daemon=True)
        self.discovery_thread.start()

    def _stop_discovery_responder(self) -> None:
        self.discovery_running = False
        if self.discovery_socket:
            try:
                self.discovery_socket.close()
            except OSError:
                pass
            self.discovery_socket = None
        if self.discovery_thread and self.discovery_thread.is_alive():
            self.discovery_thread.join(timeout=1.0)

    def _discovery_loop(self) -> None:
        while self.discovery_running and self.discovery_socket:
            try:
                payload, addr = self.discovery_socket.recvfrom(4096)
            except socket.timeout:
                continue
            except (socket.error, OSError):
                break
            try:
                message = json.loads(payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(message, dict):
                continue
            if message.get("magic") != DISCOVERY_MAGIC or message.get("type") != "discover":
                continue
            if len(self.members) >= self.max_players:
                continue
            response = {
                "magic": DISCOVERY_MAGIC,
                "type": "host_announce",
                "host_name": self.host_name,
                "machine_name": socket.gethostname(),
                "port": self.port,
                "lobby_port": self.port,
                "game_port": DEFAULT_PORT,
                "member_count": len(self.members),
                "max_players": self.max_players,
                "full": len(self.members) >= self.max_players,
            }
            try:
                self.discovery_socket.sendto(json.dumps(response, separators=(",", ":")).encode("utf-8"), addr)
            except (socket.error, OSError):
                continue


class LanLobbyClientSession:
    """Client-side LAN lobby state sync helper."""

    def __init__(self, *, player_name: str, character: str = "Caveman"):
        self.player_name = str(player_name or "Player")
        self.character = str(character or "Caveman")
        self.socket: Optional[socket.socket] = None
        self.host_address: Optional[tuple[str, int]] = None
        self.connected = False
        self.last_error: Optional[str] = None
        self.members: list[dict[str, Any]] = []
        self.host_config: dict[str, Any] = {}
        self.finalized = False

    def connect(self, host: str, port: int = LAN_LOBBY_PORT) -> bool:
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            client_socket.bind(("0.0.0.0", 0))
            client_socket.settimeout(0.05)
            self.socket = client_socket
            self.host_address = (str(host), int(port))
            self.connected = True
            self.last_error = None
            self._send_join()
            return True
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            self.close()
            return False

    def close(self) -> None:
        self.connected = False
        self.finalized = True
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None

    def discover(self, timeout: float = 2.0) -> list[dict[str, Any]]:
        finder = LanGameFinder()
        if not finder.start():
            self.last_error = finder.last_error
            return []
        started = time.time()
        hosts: list[dict[str, Any]] = []
        try:
            while time.time() - started < max(0.1, float(timeout)):
                for host in finder.poll_hosts():
                    if host.port == self.port or host.port == LAN_LOBBY_PORT:
                        hosts.append(
                            {
                                "name": host.host_name,
                                "address": host.address,
                                "port": host.port,
                            }
                        )
                time.sleep(0.05)
        finally:
            finder.close()
        return hosts

    @property
    def port(self) -> int:
        return LAN_LOBBY_PORT

    def poll(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if not self.socket:
            return messages
        while True:
            try:
                payload, _addr = self.socket.recvfrom(4096)
            except socket.timeout:
                break
            except (socket.error, OSError):
                break
            try:
                message = json.loads(payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(message, dict):
                continue
            if message.get("magic") != LAN_LOBBY_MAGIC:
                continue
            msg_type = str(message.get("type", ""))
            if msg_type == "join_ack":
                self.members = list(message.get("members", [])) if isinstance(message.get("members"), list) else []
                self.host_config = dict(message.get("host_config", {})) if isinstance(message.get("host_config"), dict) else {}
                self.connected = True
                messages.append(message)
            elif msg_type == "join_reject":
                self.last_error = str(message.get("reason", "Join rejected"))
                self.connected = False
                messages.append(message)
            elif msg_type == "lobby_state":
                self.members = list(message.get("members", [])) if isinstance(message.get("members"), list) else []
                self.host_config = dict(message.get("host_config", {})) if isinstance(message.get("host_config"), dict) else {}
                self.finalized = bool(message.get("final", False))
                messages.append(message)
        return messages

    def wait_for_final(self, timeout: float | None = None) -> dict[str, Any] | None:
        deadline = None if timeout is None else time.time() + max(0.0, float(timeout))
        while self.connected:
            for message in self.poll():
                if message.get("type") == "lobby_state" and bool(message.get("final", False)):
                    return message
            if deadline is not None and time.time() >= deadline:
                return None
            time.sleep(0.05)
        return None

    def set_character(self, character: str) -> bool:
        self.character = str(character or self.character)
        return self._send({"type": "character", "character": self.character})

    def set_ready(self, ready: bool = True) -> bool:
        return self._send({"type": "ready", "ready": bool(ready)})

    def leave(self) -> bool:
        ok = self._send({"type": "leave"})
        self.close()
        return ok

    def _send_join(self) -> bool:
        return self._send({"type": "join", "name": self.player_name, "character": self.character})

    def _send(self, payload: dict[str, Any]) -> bool:
        if not self.socket or not self.host_address:
            return False
        message = {"magic": LAN_LOBBY_MAGIC, **payload}
        try:
            self.socket.sendto(json.dumps(message, separators=(",", ":")).encode("utf-8"), self.host_address)
            return True
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            return False
