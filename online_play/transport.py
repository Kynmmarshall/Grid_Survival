"""Low-level UDP transport primitives for online play."""

from __future__ import annotations

import base64
import json
import queue
import socket
import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

from .match_flow import (
    CRITICAL_MESSAGE_TYPES,
    LATEST_ONLY_MESSAGE_TYPES,
    UNRELIABLE_MESSAGE_TYPES,
)


DEFAULT_PORT = 5555
DEFAULT_TCP_PORT = 5554  # TCP handshake on port one before UDP
GAME_UDP_PORT_OFFSET = 0

MAX_MESSAGE_BYTES = 4 * 1024 * 1024
MAX_UDP_DATAGRAM_BYTES = 1200
FRAGMENT_RAW_CHUNK_BYTES = 480
MAX_FRAGMENT_MESSAGES = 256
FRAGMENT_TTL_SECONDS = 2.5

RELIABLE_RESEND_INTERVAL = 0.09
RELIABLE_MAX_RETRIES = 36
KEEPALIVE_INTERVAL = 0.75
CONNECTION_TIMEOUT = 8.0
HELLO_RETRY_INTERVAL = 0.25
HELLO_TIMEOUT = 10.0

PKT_HELLO = "h"
PKT_HELLO_ACK = "ha"
PKT_DATA = "d"
PKT_FRAGMENT = "f"
PKT_ACK = "a"
PKT_KEEPALIVE = "k"
PKT_DISCONNECT = "x"


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


class NetworkManager:
    """Base transport manager for online-play peers."""

    _CRITICAL_MESSAGES = CRITICAL_MESSAGE_TYPES
    _LATEST_ONLY_MESSAGES = LATEST_ONLY_MESSAGE_TYPES
    _UNRELIABLE_MESSAGES = UNRELIABLE_MESSAGE_TYPES

    def __init__(self, *, is_host: bool):
        self.is_host = is_host
        self.socket: Optional[socket.socket] = None
        self.udp_socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self.listening = False
        self.receive_thread: Optional[threading.Thread] = None
        self._send_thread: Optional[threading.Thread] = None
        self.message_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._tx_seq = 0
        self._pending_lock = threading.Lock()
        self._pending_reliable: dict[tuple[int, tuple[str, int]], dict[str, Any]] = {}
        self._seen_reliable: dict[tuple[tuple[str, int], int], float] = {}
        self._fragment_buffer: dict[tuple[tuple[str, int], int], dict[str, Any]] = {}
        self._latest_messages: dict[str, dict[str, Any]] = {}
        self._latest_messages_lock = threading.Lock()
        self._last_recv_seq_by_type: dict[str, int] = {}
        self._send_queue: "queue.Queue[tuple[str, dict[str, Any], bool]]" = queue.Queue(maxsize=160)
        self._latest_outgoing: dict[str, tuple[dict[str, Any], bool]] = {}
        self._latest_outgoing_lock = threading.Lock()
        self.peer_address: Optional[tuple[str, int]] = None
        self.peer_addresses: set[tuple[str, int]] = set()
        self._peer_last_recv: dict[tuple[str, int], float] = {}
        self.udp_peer_address: Optional[tuple[str, int]] = None
        self.udp_connected = False
        self._last_recv_time = 0.0
        self._last_keepalive_sent = 0.0
        self._disconnect_notified = False
        self.last_error: Optional[str] = None

    def send_message(self, message_type: str, **payload: Any) -> bool:
        if not self.connected:
            return False
        if self.is_host and not self.peer_addresses:
            return False
        if not self.is_host and not self.peer_address:
            return False

        reliable = message_type not in self._UNRELIABLE_MESSAGES
        if message_type in self._LATEST_ONLY_MESSAGES and not reliable:
            with self._latest_outgoing_lock:
                self._latest_outgoing[message_type] = (dict(payload), reliable)
            return True

        item = (message_type, dict(payload), reliable)
        if message_type in self._CRITICAL_MESSAGES:
            try:
                self._send_queue.put(item, timeout=0.1)
                return True
            except queue.Full:
                self.last_error = f"Send queue full, dropped critical: {message_type}"
                return False

        try:
            self._send_queue.put_nowait(item)
            return True
        except queue.Full:
            return False

    def get_messages(self) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        while not self.message_queue.empty():
            try:
                messages.append(self.message_queue.get_nowait())
            except queue.Empty:
                break

        with self._latest_messages_lock:
            latest_input = self._latest_messages.pop("input_state", None)
            latest_snapshot = self._latest_messages.pop("snapshot", None)
            latest_world = self._latest_messages.pop("world_snapshot", None)
            latest_world_dynamic = self._latest_messages.pop("world_dynamic_snapshot", None)

        if latest_input is not None:
            messages.append(latest_input)
        if latest_snapshot is not None:
            messages.append(latest_snapshot)
        if latest_world is not None:
            messages.append(latest_world)
        if latest_world_dynamic is not None:
            messages.append(latest_world_dynamic)
        return messages

    def _start_threads(self) -> None:
        if self.running:
            return
        self.running = True
        self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True, name="udp-recv")
        self.receive_thread.start()
        self._send_thread = threading.Thread(target=self._send_loop, daemon=True, name="udp-send")
        self._send_thread.start()

    def _next_seq(self) -> int:
        self._tx_seq = (self._tx_seq + 1) & 0xFFFFFFFF
        return self._tx_seq

    def _get_send_targets(self) -> list[tuple[str, int]]:
        if self.is_host:
            return list(self.peer_addresses)
        if self.peer_address is None:
            return []
        return [self.peer_address]

    def _send_raw_datagram(self, data: bytes, *, address: tuple[str, int] | None = None) -> bool:
        sock = self.socket
        if not sock:
            return False
        destinations: list[tuple[str, int]]
        if address is not None:
            destinations = [address]
        elif self.is_host:
            destinations = list(self.peer_addresses)
        elif self.peer_address is not None:
            destinations = [self.peer_address]
        else:
            destinations = []
        if not destinations:
            return False
        sent_any = False
        for dest in destinations:
            try:
                sock.sendto(data, dest)
                sent_any = True
            except (socket.error, OSError) as exc:
                self.last_error = str(exc)
        return sent_any

    def _send_control(self, kind: str, *, address: tuple[str, int] | None = None, **payload: Any) -> bool:
        packet = {"k": kind, **payload}
        try:
            raw = json.dumps(packet, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return False
        if len(raw) > MAX_UDP_DATAGRAM_BYTES:
            return False
        return self._send_raw_datagram(raw, address=address)

    def _encode_data_datagrams(
        self,
        *,
        seq: int,
        message_type: str,
        payload: dict[str, Any],
        reliable: bool,
    ) -> list[bytes]:
        packet = {
            "k": PKT_DATA,
            "s": int(seq),
            "r": 1 if reliable else 0,
            "t": message_type,
            "p": payload,
        }
        try:
            encoded = json.dumps(packet, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        except (TypeError, ValueError, OverflowError):
            return []
        if len(encoded) > MAX_MESSAGE_BYTES:
            self.last_error = f"Message too large: {len(encoded)} bytes"
            return []
        if len(encoded) <= MAX_UDP_DATAGRAM_BYTES:
            return [encoded]

        chunks: list[bytes] = []
        total = (len(encoded) + FRAGMENT_RAW_CHUNK_BYTES - 1) // FRAGMENT_RAW_CHUNK_BYTES
        for idx in range(total):
            start = idx * FRAGMENT_RAW_CHUNK_BYTES
            end = min(len(encoded), start + FRAGMENT_RAW_CHUNK_BYTES)
            raw_chunk = encoded[start:end]
            frag = {
                "k": PKT_FRAGMENT,
                "s": int(seq),
                "r": 1 if reliable else 0,
                "i": int(idx),
                "n": int(total),
                "x": base64.b64encode(raw_chunk).decode("ascii"),
            }
            try:
                frag_bytes = json.dumps(frag, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            except (TypeError, ValueError, OverflowError):
                return []
            if len(frag_bytes) > MAX_UDP_DATAGRAM_BYTES:
                self.last_error = "Fragment too large for UDP datagram budget"
                return []
            chunks.append(frag_bytes)
        return chunks

    def _queue_or_latest_message(
        self,
        message: dict[str, Any],
        seq: int | None = None,
        address: tuple[str, int] | None = None,
    ) -> None:
        msg_type = message.get("type")
        if not isinstance(msg_type, str):
            return
        if self.is_host and msg_type == "input_state":
            self.message_queue.put(message)
            return
        if msg_type in self._LATEST_ONLY_MESSAGES and isinstance(seq, int):
            last = self._last_recv_seq_by_type.get(msg_type)
            if last is not None and seq <= last:
                return
            self._last_recv_seq_by_type[msg_type] = seq
            with self._latest_messages_lock:
                self._latest_messages[msg_type] = message
            return
        self.message_queue.put(message)

    def _cleanup_runtime_state(self, now: float) -> None:
        stale_seen = [key for key, ts in self._seen_reliable.items() if now - ts > 30.0]
        for key in stale_seen:
            self._seen_reliable.pop(key, None)

        stale_frag = [
            key
            for key, entry in self._fragment_buffer.items()
            if now - float(entry.get("created", now)) > FRAGMENT_TTL_SECONDS
        ]
        for key in stale_frag:
            self._fragment_buffer.pop(key, None)

        if len(self._fragment_buffer) > MAX_FRAGMENT_MESSAGES:
            ordered = sorted(
                self._fragment_buffer.items(),
                key=lambda kv: float(kv[1].get("created", now)),
            )
            to_drop = len(self._fragment_buffer) - MAX_FRAGMENT_MESSAGES
            for key, _entry in ordered[:to_drop]:
                self._fragment_buffer.pop(key, None)

    def _resend_reliables(self, now: float) -> None:
        if not self.connected:
            return
        timed_out = False
        timed_out_peers: set[tuple[str, int]] = set()
        with self._pending_lock:
            for pending_key, entry in list(self._pending_reliable.items()):
                last_sent = float(entry.get("last_sent", 0.0))
                retries = int(entry.get("retries", 0))
                if now - last_sent < RELIABLE_RESEND_INTERVAL:
                    continue
                datagrams: list[bytes] = entry.get("datagrams", [])
                _seq, target = pending_key
                for dgram in datagrams:
                    self._send_raw_datagram(dgram, address=target)
                retries += 1
                entry["last_sent"] = now
                entry["retries"] = retries
                if retries > RELIABLE_MAX_RETRIES:
                    self._pending_reliable.pop(pending_key, None)
                    if self.is_host:
                        timed_out_peers.add(target)
                    else:
                        timed_out = True
        for peer in timed_out_peers:
            self._drop_host_peer(peer, notify=True)
        if timed_out and self.connected and not self.is_host:
            self.last_error = "Reliable UDP delivery timed out"
            self._mark_disconnected(notify=True)

    def _flush_latest_outgoing(self) -> None:
        if not self.connected:
            return
        with self._latest_outgoing_lock:
            pending = list(self._latest_outgoing.items())
            self._latest_outgoing.clear()
        for msg_type, (payload, reliable) in pending:
            seq = self._next_seq()
            datagrams = self._encode_data_datagrams(
                seq=seq,
                message_type=msg_type,
                payload=payload,
                reliable=reliable,
            )
            targets = self._get_send_targets()
            for target in targets:
                for dgram in datagrams:
                    self._send_raw_datagram(dgram, address=target)
            if reliable:
                with self._pending_lock:
                    for target in targets:
                        self._pending_reliable[(seq, target)] = {
                            "datagrams": datagrams,
                            "last_sent": time.time(),
                            "retries": 0,
                            "message_type": msg_type,
                        }

    def _send_keepalive_if_needed(self, now: float) -> None:
        if self.connected and now - self._last_keepalive_sent >= KEEPALIVE_INTERVAL:
            if self._send_control(PKT_KEEPALIVE, ts=now):
                self._last_keepalive_sent = now

    def _check_connection_timeout(self, now: float) -> None:
        if self.is_host:
            stale_peers = [
                peer
                for peer, seen_at in self._peer_last_recv.items()
                if now - seen_at > CONNECTION_TIMEOUT
            ]
            for peer in stale_peers:
                self._drop_host_peer(peer, notify=True)
            return
        if self.connected and now - self._last_recv_time > CONNECTION_TIMEOUT:
            self.last_error = "Network timeout"
            self._mark_disconnected(notify=True)

    def _send_loop(self) -> None:
        while self.running:
            now = time.time()
            self._cleanup_runtime_state(now)
            self._resend_reliables(now)
            self._send_keepalive_if_needed(now)
            self._flush_latest_outgoing()
            self._check_connection_timeout(now)
            try:
                msg_type, payload, reliable = self._send_queue.get(timeout=0.02)
            except queue.Empty:
                continue
            if not self.connected:
                continue
            seq = self._next_seq()
            datagrams = self._encode_data_datagrams(
                seq=seq,
                message_type=msg_type,
                payload=payload,
                reliable=reliable,
            )
            if not datagrams:
                continue
            targets = self._get_send_targets()
            for target in targets:
                for dgram in datagrams:
                    self._send_raw_datagram(dgram, address=target)
            if reliable:
                with self._pending_lock:
                    for target in targets:
                        self._pending_reliable[(seq, target)] = {
                            "datagrams": datagrams,
                            "last_sent": now,
                            "retries": 0,
                            "message_type": msg_type,
                        }

    def _handle_ack(self, packet: dict[str, Any], address: tuple[str, int]) -> None:
        seq = packet.get("s")
        if isinstance(seq, int):
            with self._pending_lock:
                self._pending_reliable.pop((seq, address), None)

    def _handle_data_packet(self, packet: dict[str, Any], address: tuple[str, int]) -> None:
        seq = packet.get("s")
        msg_type = packet.get("t")
        payload = packet.get("p")
        reliable = bool(packet.get("r", 0))
        if not isinstance(seq, int) or not isinstance(msg_type, str):
            return
        if not isinstance(payload, dict):
            payload = {}
        if reliable:
            seen_key = (address, seq)
            if seen_key in self._seen_reliable:
                self._send_control(PKT_ACK, address=address, s=seq)
                return
            self._seen_reliable[seen_key] = time.time()
            self._send_control(PKT_ACK, address=address, s=seq)
        message = {"type": msg_type, **payload}
        if self.is_host:
            message["_from"] = address
        if msg_type == "disconnect":
            if self.is_host:
                self._drop_host_peer(address, notify=False)
            else:
                self._queue_or_latest_message({"type": "disconnect"}, seq=seq)
                self._mark_disconnected(notify=False)
            return
        self._queue_or_latest_message(message, seq=seq, address=address)

    def _handle_fragment(self, packet: dict[str, Any], address: tuple[str, int]) -> None:
        seq = packet.get("s")
        idx = packet.get("i")
        total = packet.get("n")
        frag_b64 = packet.get("x")
        reliable = bool(packet.get("r", 0))
        if not isinstance(seq, int) or not isinstance(idx, int) or not isinstance(total, int):
            return
        if not isinstance(frag_b64, str) or total <= 0 or idx < 0 or idx >= total:
            return
        seen_key = (address, seq)
        if reliable and seen_key in self._seen_reliable:
            self._send_control(PKT_ACK, address=address, s=seq)
            return
        try:
            chunk = base64.b64decode(frag_b64.encode("ascii"), validate=True)
        except (ValueError, base64.binascii.Error):
            return
        frag_key = (address, seq)
        entry = self._fragment_buffer.get(frag_key)
        now = time.time()
        if entry is None:
            entry = {"created": now, "total": total, "reliable": reliable, "parts": {}}
            self._fragment_buffer[frag_key] = entry
        if int(entry.get("total", total)) != total:
            self._fragment_buffer.pop(frag_key, None)
            return
        parts: dict[int, bytes] = entry["parts"]
        if idx not in parts:
            parts[idx] = chunk
        if len(parts) != total:
            return
        self._fragment_buffer.pop(frag_key, None)
        try:
            assembled = b"".join(parts[i] for i in range(total))
        except KeyError:
            return
        if len(assembled) > MAX_MESSAGE_BYTES:
            return
        try:
            data_packet = json.loads(assembled.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if isinstance(data_packet, dict) and data_packet.get("k") == PKT_DATA:
            self._handle_data_packet(data_packet, address)

    def _drop_host_peer(self, address: tuple[str, int], *, notify: bool) -> None:
        if not self.is_host:
            return
        if address in self.peer_addresses:
            self.peer_addresses.discard(address)
            self._peer_last_recv.pop(address, None)
            with self._pending_lock:
                stale_keys = [key for key in self._pending_reliable if key[1] == address]
                for key in stale_keys:
                    self._pending_reliable.pop(key, None)
            if self.peer_address == address:
                self.peer_address = next(iter(self.peer_addresses), None)
            self.udp_peer_address = self.peer_address
        self.connected = bool(self.peer_addresses)
        self.udp_connected = self.connected
        if notify and not self.connected and not self._disconnect_notified:
            self.message_queue.put({"type": "disconnect"})
            self._disconnect_notified = True

    def _mark_disconnected(self, *, notify: bool) -> None:
        was_connected = bool(self.connected)
        self.connected = False
        self.udp_connected = False
        if self.is_host:
            self.peer_addresses.clear()
            self._peer_last_recv.clear()
            self.peer_address = None
            self.udp_peer_address = None
        with self._pending_lock:
            self._pending_reliable.clear()
        with self._latest_outgoing_lock:
            self._latest_outgoing.clear()
        self._fragment_buffer.clear()
        self._last_recv_seq_by_type.clear()
        if notify and was_connected and not self._disconnect_notified:
            self.message_queue.put({"type": "disconnect"})
            self._disconnect_notified = True

    def _address_matches_peer(self, address: tuple[str, int]) -> bool:
        if self.is_host:
            return address in self.peer_addresses
        if self.peer_address is None:
            return False
        return address[0] == self.peer_address[0] and address[1] == self.peer_address[1]

    def _handle_hello(self, address: tuple[str, int]) -> None:
        if not self.is_host:
            return
        self.peer_addresses.add(address)
        self.peer_address = self.peer_address or address
        self.udp_peer_address = address
        self.connected = True
        self.udp_connected = True
        self._disconnect_notified = False
        now = time.time()
        self._last_recv_time = now
        self._peer_last_recv[address] = now
        self._send_control(PKT_HELLO_ACK, address=address, ts=now)

    def _handle_hello_ack(self, address: tuple[str, int]) -> None:
        if self.is_host or self.peer_address is None:
            return
        if address[0] != self.peer_address[0] or address[1] != self.peer_address[1]:
            return
        self.connected = True
        self.udp_connected = True
        self._disconnect_notified = False
        self._last_recv_time = time.time()

    def _receive_loop(self) -> None:
        while self.running and self.socket:
            try:
                payload, address = self.socket.recvfrom(MAX_UDP_DATAGRAM_BYTES * 2)
            except socket.timeout:
                continue
            except (socket.error, OSError):
                break
            if not payload or len(payload) > MAX_MESSAGE_BYTES:
                continue
            try:
                packet = json.loads(payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if not isinstance(packet, dict):
                continue
            kind = packet.get("k")
            if kind == PKT_HELLO:
                self._handle_hello(address)
                continue
            if kind == PKT_HELLO_ACK:
                self._handle_hello_ack(address)
                continue
            if not self._address_matches_peer(address):
                continue
            now = time.time()
            self._last_recv_time = now
            if self.is_host:
                self._peer_last_recv[address] = now
            if kind == PKT_ACK:
                self._handle_ack(packet, address)
            elif kind == PKT_KEEPALIVE:
                pass
            elif kind == PKT_DISCONNECT:
                if self.is_host:
                    self._drop_host_peer(address, notify=True)
                else:
                    self._mark_disconnected(notify=True)
            elif kind == PKT_DATA:
                self._handle_data_packet(packet, address)
            elif kind == PKT_FRAGMENT:
                self._handle_fragment(packet, address)
        if not self.is_host and self.connected:
            self._mark_disconnected(notify=True)

    def disconnect(self) -> None:
        if self.connected and self.socket and (self.peer_address or self.peer_addresses):
            self._send_control(PKT_DISCONNECT)
            self._send_control(PKT_DISCONNECT)
        self.running = False
        self.connected = False
        self.udp_connected = False
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except queue.Empty:
                break
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None
            self.udp_socket = None
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)
        if self._send_thread and self._send_thread.is_alive():
            self._send_thread.join(timeout=1.0)
        self.peer_address = None
        self.peer_addresses.clear()
        self._peer_last_recv.clear()
        self.udp_peer_address = None
        with self._pending_lock:
            self._pending_reliable.clear()
        with self._latest_outgoing_lock:
            self._latest_outgoing.clear()
        with self._latest_messages_lock:
            self._latest_messages.clear()
        self._seen_reliable.clear()
        self._fragment_buffer.clear()
        self._last_recv_seq_by_type.clear()


class UdpHostTransport(NetworkManager):
    """UDP host transport without lobby or discovery concerns."""

    def __init__(self, port: int = DEFAULT_PORT):
        super().__init__(is_host=True)
        self.port = int(port)
        self.server_socket: Optional[socket.socket] = None

    def start_hosting(self) -> bool:
        try:
            host_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            host_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            host_socket.bind(("0.0.0.0", self.port))
            host_socket.settimeout(0.05)
            self.socket = host_socket
            self.udp_socket = host_socket
            self.running = False
            self.connected = False
            self.udp_connected = False
            self.peer_address = None
            self.udp_peer_address = None
            self.last_error = None
            self._start_threads()
            self.listening = True
            return True
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            self.listening = False
            if self.socket:
                try:
                    self.socket.close()
                except OSError:
                    pass
                self.socket = None
                self.udp_socket = None
            return False

    def poll_connection(self) -> bool:
        return bool(self.connected)

    def wait_for_connection(self, timeout: float = 30.0) -> bool:
        deadline = time.time() + max(0.0, float(timeout))
        while time.time() < deadline:
            if self.connected:
                return True
            time.sleep(0.05)
        return False


class UdpClientTransport(NetworkManager):
    """UDP client transport without matchmaking concerns."""

    def __init__(self):
        super().__init__(is_host=False)
        self.tcp_auth_token = None  # Store token from successful TCP auth

    def _tcp_handshake(self, host: str, port: int, token: str, player_name: str, timeout: float = 5.0) -> bool:
        """Perform authentication handshake via TCP before UDP connection.
        
        Returns True if successful, False otherwise.
        On success, sets self.tcp_auth_token and session_id.
        """
        tcp_port = port - 1  # TCP is on port one before UDP
        tcp_sock = None
        try:
            tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_sock.settimeout(timeout)
            
            # Connect to TCP server
            try:
                tcp_sock.connect((host, tcp_port))
            except (socket.error, OSError) as e:
                self.last_error = f"TCP connection failed: {e}"
                return False
            
            # Send hello via TCP
            hello_msg = json.dumps({"type": "hello"}, separators=(",", ":"), ensure_ascii=True)
            try:
                tcp_sock.send(hello_msg.encode("utf-8") + b"\n")
            except (socket.error, OSError) as e:
                self.last_error = f"TCP send hello failed: {e}"
                tcp_sock.close()
                return False
            
            # Receive hello_ack via TCP
            try:
                data = tcp_sock.recv(4096)
                if not data:
                    self.last_error = "TCP connection closed unexpectedly"
                    tcp_sock.close()
                    return False
                hello_ack_msg = json.loads(data.decode("utf-8").strip())
                if hello_ack_msg.get("type") != "hello_ack":
                    self.last_error = f"Unexpected TCP response: {hello_ack_msg.get('type')}"
                    tcp_sock.close()
                    return False
            except (json.JSONDecodeError, socket.error, OSError) as e:
                self.last_error = f"TCP receive hello_ack failed: {e}"
                tcp_sock.close()
                return False
            
            # Send internet_auth via TCP
            auth_msg = json.dumps({
                "type": "internet_auth",
                "token": str(token),
                "player": str(player_name)
            }, separators=(",", ":"), ensure_ascii=True)
            try:
                tcp_sock.send(auth_msg.encode("utf-8") + b"\n")
            except (socket.error, OSError) as e:
                self.last_error = f"TCP send auth failed: {e}"
                tcp_sock.close()
                return False
            
            # Receive internet_auth_ok via TCP
            try:
                data = tcp_sock.recv(4096)
                if not data:
                    self.last_error = "TCP connection closed before auth confirmation"
                    tcp_sock.close()
                    return False
                auth_ok_msg = json.loads(data.decode("utf-8").strip())
                if auth_ok_msg.get("type") != "internet_auth_ok":
                    if auth_ok_msg.get("type") == "internet_auth_error":
                        self.last_error = f"Auth error: {auth_ok_msg.get('error', 'unknown')}"
                    else:
                        self.last_error = f"Unexpected TCP response: {auth_ok_msg.get('type')}"
                    tcp_sock.close()
                    return False
                
                # Store session info
                self.tcp_auth_token = str(token)
                self.session_id = str(auth_ok_msg.get("session_id", ""))
                try:
                    print(f"[DEBUG] TCP handshake successful, session_id={self.session_id}")
                except Exception:
                    pass
                
            except (json.JSONDecodeError, socket.error, OSError) as e:
                self.last_error = f"TCP receive auth_ok failed: {e}"
                tcp_sock.close()
                return False
            
            tcp_sock.close()
            return True
            
        except Exception as e:
            self.last_error = f"TCP handshake exception: {e}"
            if tcp_sock:
                try:
                    tcp_sock.close()
                except Exception:
                    pass
            return False

    def _setup_udp_socket(self, host: str, port: int = DEFAULT_PORT) -> bool:
        """Setup UDP socket and threads WITHOUT waiting for hello_ack.
        
        Used when TCP auth happens instead of UDP hello handshake.
        Returns True if socket is ready, False on error.
        """
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            client_socket.bind(("0.0.0.0", 0))
            client_socket.settimeout(0.05)
            self.socket = client_socket
            self.udp_socket = client_socket
            self.peer_address = (host, int(port))
            self.udp_peer_address = self.peer_address
            self.last_error = None
            self._disconnect_notified = False
            self._last_recv_time = time.time()
            self._start_threads()
            try:
                print(f"[DEBUG] UDP socket ready for {host}:{port} (no hello wait)")
            except Exception:
                pass
            return True
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            if self.socket:
                try:
                    self.socket.close()
                except OSError:
                    pass
                self.socket = None
                self.udp_socket = None
            return False

    def connect_to_host(self, host: str, port: int = DEFAULT_PORT) -> bool:
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            client_socket.bind(("0.0.0.0", 0))
            client_socket.settimeout(0.05)
            self.socket = client_socket
            self.udp_socket = client_socket
            self.peer_address = (host, int(port))
            self.udp_peer_address = self.peer_address
            self.connected = False
            self.udp_connected = False
            self.last_error = None
            self._disconnect_notified = False
            self._last_recv_time = time.time()
            self._start_threads()
            deadline = time.time() + HELLO_TIMEOUT
            next_hello = 0.0
            hello_sent = 0
            while self.running and not self.connected and time.time() < deadline:
                now = time.time()
                if now >= next_hello:
                    self._send_control(PKT_HELLO, ts=now)
                    hello_sent += 1
                    if hello_sent <= 3 or hello_sent % 10 == 0:
                        try:
                            print(f"[DEBUG] hello sent #{hello_sent} to {self.peer_address}")
                        except Exception:
                            pass
                    next_hello = now + HELLO_RETRY_INTERVAL
                time.sleep(0.02)
            if self.connected:
                return True
            self.last_error = "Unable to establish UDP session with host"
            self.disconnect()
            return False
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            self.connected = False
            self.udp_connected = False
            if self.socket:
                try:
                    self.socket.close()
                except OSError:
                    pass
                self.socket = None
                self.udp_socket = None
            return False
