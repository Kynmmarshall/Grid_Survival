"""
LAN multiplayer networking for Grid Survival.

The host runs the authoritative simulation. The client sends input updates and
receives world snapshots back over a simple length-prefixed JSON protocol.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional


DEFAULT_PORT = 5555
DISCOVERY_PORT = 5556
DISCOVERY_MAGIC = "grid_survival_lan_v1"
DISCOVERY_HOST_MAX_AGE = 4.0


@dataclass
class InputState:
    """Pressed-state payload sent from the client to the host."""

    up: bool = False
    down: bool = False
    left: bool = False
    right: bool = False
    jump: bool = False
    power_pressed: bool = False

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "InputState":
        if not isinstance(data, dict):
            return cls()
        return cls(
            up=bool(data.get("up", False)),
            down=bool(data.get("down", False)),
            left=bool(data.get("left", False)),
            right=bool(data.get("right", False)),
            jump=bool(data.get("jump", False)),
            power_pressed=bool(data.get("power_pressed", False)),
        )

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass
class PlayerState:
    """Legacy-compatible player state payload."""

    x: float
    y: float
    facing: str
    state: str
    falling: bool
    drowning: bool
    eliminated: bool


@dataclass
class DiscoveredHost:
    """A host discovered on the local network."""

    host_name: str
    machine_name: str
    address: str
    port: int
    last_seen: float


class NetworkManager:
    """Base network manager for LAN multiplayer."""

    def __init__(self, *, is_host: bool):
        self.is_host = is_host
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self.receive_thread: Optional[threading.Thread] = None
        self.message_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._send_lock = threading.Lock()
        self.peer_address: Optional[tuple[str, int]] = None
        self.last_error: Optional[str] = None

    def send_message(self, message_type: str, **payload: Any) -> bool:
        """Send a framed JSON message to the connected peer."""
        if not self.connected or not self.socket:
            return False

        try:
            message = {"type": message_type, **payload}
            encoded = json.dumps(message, separators=(",", ":")).encode("utf-8")
            header = len(encoded).to_bytes(4, "big")
            with self._send_lock:
                self.socket.sendall(header)
                self.socket.sendall(encoded)
            return True
        except (socket.error, BrokenPipeError, OSError) as exc:
            self.last_error = str(exc)
            self.connected = False
            return False

    def get_messages(self) -> list[dict[str, Any]]:
        """Return all queued messages received since the last call."""
        messages: list[dict[str, Any]] = []
        while not self.message_queue.empty():
            try:
                messages.append(self.message_queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def _start_receive_loop(self) -> None:
        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
        self.receive_thread.start()

    def _receive_loop(self) -> None:
        while self.running and self.connected and self.socket:
            try:
                length_bytes = self._recv_exact(4)
                if not length_bytes:
                    break

                length = int.from_bytes(length_bytes, "big")
                if length <= 0:
                    continue

                payload = self._recv_exact(length)
                if not payload:
                    break

                message = json.loads(payload.decode("utf-8"))
                if isinstance(message, dict):
                    self.message_queue.put(message)
            except (socket.error, OSError, json.JSONDecodeError) as exc:
                self.last_error = str(exc)
                break

        self.connected = False
        self.running = False

    def _recv_exact(self, size: int) -> Optional[bytes]:
        if not self.socket:
            return None

        chunks = bytearray()
        while len(chunks) < size and self.running:
            try:
                chunk = self.socket.recv(size - len(chunks))
            except socket.timeout:
                continue
            except (socket.error, OSError):
                return None
            if not chunk:
                return None
            chunks.extend(chunk)
        return bytes(chunks)

    def disconnect(self) -> None:
        self.running = False
        self.connected = False
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)


class NetworkHost(NetworkManager):
    """Host-side connection manager supporting up to 8 players."""

    def __init__(self, port: int = DEFAULT_PORT):
        super().__init__(is_host=True)
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.listening = False
        self.advertised_name = "Host"
        self.machine_name = socket.gethostname()
        self.discovery_socket: Optional[socket.socket] = None
        self.discovery_thread: Optional[threading.Thread] = None
        self.discovery_running = False
        self.max_players = 8
        self._clients: dict[int, "NetworkManager"] = {}
        self._next_client_id = 0
        self._accept_lock = threading.Lock()

    def start_hosting(self, advertised_name: str | None = None) -> bool:
        """Start listening for up to 8 LAN clients without blocking the UI thread."""
        try:
            if advertised_name:
                self.advertised_name = advertised_name
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", self.port))
            self.server_socket.listen(self.max_players)
            self.server_socket.setblocking(False)
            self._start_discovery_responder()
            self.listening = True
            self.last_error = None
            return True
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            self.listening = False
            if self.server_socket:
                try:
                    self.server_socket.close()
                except OSError:
                    pass
                self.server_socket = None
            self._stop_discovery_responder()
            return False

    def poll_connections(self) -> list[int]:
        """Accept all waiting clients and return list of new client IDs."""
        new_ids = []
        if not self.server_socket or not self.listening:
            return new_ids
        
        if len(self._clients) >= self.max_players:
            return new_ids
        
        while len(self._clients) < self.max_players:
            try:
                client_socket, addr = self.server_socket.accept()
            except BlockingIOError:
                break
            except (socket.error, OSError) as exc:
                self.last_error = str(exc)
                break

            client_id = self._next_client_id
            self._next_client_id += 1
            
            client_socket.settimeout(0.25)
            client_manager = NetworkManager(is_host=True)
            client_manager.socket = client_socket
            client_manager.peer_address = addr
            client_manager.connected = True
            client_manager._start_receive_loop()
            
            self._clients[client_id] = client_manager
            new_ids.append(client_id)
        
        return new_ids

    def poll_connection(self) -> bool:
        """Legacy single-client compatibility."""
        new_ids = self.poll_connections()
        return len(new_ids) > 0 or len(self._clients) > 0

    def get_client_count(self) -> int:
        """Return number of connected clients."""
        return len(self._clients)

    def get_client(self, client_id: int) -> Optional["NetworkManager"]:
        """Get a specific client manager."""
        return self._clients.get(client_id)

    def remove_client(self, client_id: int) -> None:
        """Remove a client by ID."""
        if client_id in self._clients:
            self._clients[client_id].disconnect()
            del self._clients[client_id]

    def get_all_messages(self) -> dict[int, list[dict]]:
        """Get all messages from all clients grouped by client ID."""
        messages = {}
        for client_id, client in self._clients.items():
            client_messages = client.get_messages()
            if client_messages:
                messages[client_id] = client_messages
        return messages

    def broadcast_message(self, message_type: str, **payload: Any) -> int:
        """Send a message to all connected clients. Returns count of successful sends."""
        sent_count = 0
        for client in self._clients.values():
            if client.send_message(message_type, **payload):
                sent_count += 1
        return sent_count

    def wait_for_connection(self, timeout: float = 30.0) -> bool:
        """Wait for at least one client connection (legacy compatibility)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.poll_connections():
                return True
            time.sleep(0.05)
        return False

    def disconnect(self) -> None:
        for client in list(self._clients.values()):
            client.disconnect()
        self._clients.clear()
        super().disconnect()
        self.listening = False
        self._stop_discovery_responder()
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None

    def _start_discovery_responder(self) -> None:
        self.discovery_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.discovery_socket.bind(("0.0.0.0", DISCOVERY_PORT))
        self.discovery_socket.settimeout(0.25)
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
            if self.connected:
                continue

            response = {
                "magic": DISCOVERY_MAGIC,
                "type": "host_announce",
                "host_name": self.advertised_name,
                "machine_name": self.machine_name,
                "port": self.port,
            }
            try:
                self.discovery_socket.sendto(
                    json.dumps(response, separators=(",", ":")).encode("utf-8"),
                    addr,
                )
            except (socket.error, OSError):
                continue


class NetworkClient(NetworkManager):
    """Client-side connection manager."""

    def __init__(self):
        super().__init__(is_host=False)

    def connect_to_host(self, host: str, port: int = DEFAULT_PORT) -> bool:
        """Connect to the host over TCP."""
        try:
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.settimeout(10.0)
            client.connect((host, port))
            client.settimeout(0.25)
            self.socket = client
            self.peer_address = (host, port)
            self.connected = True
            self.last_error = None
            self._start_receive_loop()
            return True
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except OSError:
                    pass
                self.socket = None
            return False


class LanGameFinder:
    """Broadcast for LAN hosts and collect their announcements."""

    def __init__(self):
        self.socket: Optional[socket.socket] = None
        self.last_error: Optional[str] = None
        self._hosts: dict[tuple[str, int], DiscoveredHost] = {}

    def start(self) -> bool:
        try:
            finder_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            finder_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            finder_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            finder_socket.bind(("0.0.0.0", 0))
            finder_socket.settimeout(0.05)
            self.socket = finder_socket
            self.last_error = None
            self.probe()
            return True
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            self.close()
            return False

    def close(self) -> None:
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None

    def probe(self) -> None:
        if not self.socket:
            return

        probe = {
            "magic": DISCOVERY_MAGIC,
            "type": "discover",
            "timestamp": time.time(),
        }
        encoded = json.dumps(probe, separators=(",", ":")).encode("utf-8")
        for address in _candidate_broadcast_addresses():
            try:
                self.socket.sendto(encoded, (address, DISCOVERY_PORT))
            except (socket.error, OSError):
                continue

    def poll_hosts(self) -> list[DiscoveredHost]:
        if not self.socket:
            return []

        now = time.time()
        while True:
            try:
                payload, addr = self.socket.recvfrom(4096)
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
            if message.get("magic") != DISCOVERY_MAGIC or message.get("type") != "host_announce":
                continue

            port = int(message.get("port", DEFAULT_PORT))
            key = (addr[0], port)
            self._hosts[key] = DiscoveredHost(
                host_name=str(message.get("host_name", "Host")),
                machine_name=str(message.get("machine_name", addr[0])),
                address=addr[0],
                port=port,
                last_seen=now,
            )

        active_hosts = [
            host
            for host in self._hosts.values()
            if now - host.last_seen <= DISCOVERY_HOST_MAX_AGE
        ]
        self._hosts = {(host.address, host.port): host for host in active_hosts}
        return sorted(active_hosts, key=lambda host: (host.host_name.lower(), host.address))


def _candidate_broadcast_addresses() -> list[str]:
    addresses = ["255.255.255.255"]
    local_ip = get_local_ip()
    parts = local_ip.split(".")
    if len(parts) == 4 and local_ip != "127.0.0.1":
        subnet_broadcast = ".".join(parts[:3] + ["255"])
        if subnet_broadcast not in addresses:
            addresses.append(subnet_broadcast)
    return addresses


def get_local_ip() -> str:
    """Best-effort local IPv4 address for LAN hosting."""
    sock: Optional[socket.socket] = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        if sock:
            try:
                sock.close()
            except OSError:
                pass
