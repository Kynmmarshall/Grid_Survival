"""
LAN multiplayer networking for Grid Survival.

The host runs the authoritative simulation. The client sends input updates and
receives world snapshots back over a hybrid transport:

- TCP for reliable control/state messages.
- UDP for high-frequency input and snapshot traffic.
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
GAME_UDP_PORT_OFFSET = 1
DISCOVERY_PORT = 5556
DISCOVERY_MAGIC = "grid_survival_lan_v1"
DISCOVERY_HOST_MAX_AGE = 4.0
UDP_HANDSHAKE_TYPE = "udp_hello"
UDP_READY_TYPE = "udp_ready"

# Guard against corrupted or malicious length prefixes that would cause OOM
MAX_MESSAGE_BYTES = 4 * 1024 * 1024  # 4 MB
# Keep UDP packets reasonably sized to avoid heavy fragmentation.
MAX_UDP_MESSAGE_BYTES = 60 * 1024


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

    # Message types that must never be dropped even when the TCP send queue is full.
    _CRITICAL_MESSAGES = frozenset(
        {
            "disconnect",
            "game_start",
            "pause_state",
            "pause_toggle_request",
            "restart_request",
            "player_setup",
        }
    )
    # High-frequency gameplay traffic prefers UDP, with automatic TCP fallback.
    _UDP_PREFERRED_MESSAGES = frozenset({"input_state", "snapshot"})
    # Keep only the latest packet for high-frequency stream types.
    _LATEST_ONLY_MESSAGES = frozenset({"input_state", "snapshot", "world_snapshot"})

    def __init__(self, *, is_host: bool):
        self.is_host = is_host
        self.socket: Optional[socket.socket] = None
        self.udp_socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self.receive_thread: Optional[threading.Thread] = None
        self.udp_receive_thread: Optional[threading.Thread] = None
        # Bounded async send queue: prevents the main game loop from ever blocking
        # on socket.sendall().  128 slots ≈ ~4 seconds of input messages at 30 Hz.
        self._send_queue: "queue.Queue[bytes]" = queue.Queue(maxsize=128)
        self._send_thread: Optional[threading.Thread] = None
        self.message_queue: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self._latest_messages: dict[str, dict[str, Any]] = {}
        self._latest_messages_lock = threading.Lock()
        self.peer_address: Optional[tuple[str, int]] = None
        self.udp_peer_address: Optional[tuple[str, int]] = None
        self.udp_connected = False
        self._udp_send_seq = 0
        self._udp_last_recv_seq: dict[str, int] = {}
        self._last_udp_hello_time = 0.0
        self.last_error: Optional[str] = None

    def send_message(self, message_type: str, **payload: Any) -> bool:
        """Enqueue a framed JSON message for async delivery to the peer.

        Returns True when the message was accepted into the send queue.
        UDP-preferred messages are attempted first and transparently fall back
        to TCP when UDP is unavailable.
        """
        if not self.connected:
            return False

        if message_type in self._UDP_PREFERRED_MESSAGES:
            # Client retries UDP hello until the host confirms the UDP path.
            if not self.is_host and not self.udp_connected:
                self._maybe_send_udp_hello()
            if self._send_udp_message(message_type, **payload):
                return True

        try:
            message = {"type": message_type, **payload}
            encoded = json.dumps(message, separators=(",", ":")).encode("utf-8")
            header = len(encoded).to_bytes(4, "big")
            data = header + encoded
        except (TypeError, ValueError, OverflowError) as exc:
            self.last_error = str(exc)
            return False

        if message_type in self._CRITICAL_MESSAGES:
            # Block for up to 100 ms to guarantee delivery of critical messages.
            try:
                self._send_queue.put(data, timeout=0.1)
                return True
            except queue.Full:
                self.last_error = f"Send queue full, dropped critical: {message_type}"
                return False
        else:
            # Non-critical: drop immediately if the queue is saturated.
            try:
                self._send_queue.put_nowait(data)
                return True
            except queue.Full:
                return False

    def _maybe_send_udp_hello(self) -> None:
        if self.is_host:
            return
        if not self.connected or not self.udp_socket or not self.udp_peer_address:
            return
        now = time.time()
        if now - self._last_udp_hello_time < 0.35:
            return
        self._last_udp_hello_time = now
        self._send_udp_control(UDP_HANDSHAKE_TYPE, timestamp=now)

    def _send_udp_control(
        self,
        message_type: str,
        *,
        address: tuple[str, int] | None = None,
        **payload: Any,
    ) -> bool:
        if not self.udp_socket:
            return False
        destination = address or self.udp_peer_address
        if not destination:
            return False

        try:
            encoded = json.dumps(
                {"type": message_type, **payload}, separators=(",", ":")
            ).encode("utf-8")
            if len(encoded) > MAX_UDP_MESSAGE_BYTES:
                return False
            self.udp_socket.sendto(encoded, destination)
            return True
        except (TypeError, ValueError, OverflowError, socket.error, OSError):
            return False

    def _next_udp_seq(self) -> int:
        self._udp_send_seq = (self._udp_send_seq + 1) & 0xFFFFFFFF
        return self._udp_send_seq

    def _send_udp_message(self, message_type: str, **payload: Any) -> bool:
        if (
            not self.connected
            or not self.udp_connected
            or not self.udp_socket
            or not self.udp_peer_address
        ):
            return False

        try:
            message = {"type": message_type, "_seq": self._next_udp_seq(), **payload}
            encoded = json.dumps(message, separators=(",", ":")).encode("utf-8")
            if len(encoded) > MAX_UDP_MESSAGE_BYTES:
                return False
            self.udp_socket.sendto(encoded, self.udp_peer_address)
            return True
        except (TypeError, ValueError, OverflowError, socket.error, OSError) as exc:
            self.last_error = str(exc)
            return False

    def _can_accept_udp_peer(self, address: tuple[str, int]) -> bool:
        if self.is_host and self.peer_address:
            return address[0] == self.peer_address[0]
        return True

    def _accept_udp_payload_sender(self, address: tuple[str, int]) -> bool:
        if self.udp_peer_address is None:
            return self._can_accept_udp_peer(address)
        return address == self.udp_peer_address

    def _set_udp_peer(self, address: tuple[str, int]) -> None:
        if not self._can_accept_udp_peer(address):
            return
        self.udp_peer_address = address
        self.udp_connected = True

    def _queue_message(self, message: dict[str, Any], *, via_udp: bool = False) -> None:
        if not isinstance(message, dict):
            return

        if via_udp:
            message_type = message.get("type")
            sequence = message.get("_seq")
            if isinstance(message_type, str) and isinstance(sequence, int):
                last_seq = self._udp_last_recv_seq.get(message_type)
                if last_seq is not None and sequence <= last_seq:
                    return
                self._udp_last_recv_seq[message_type] = sequence

        cleaned = dict(message)
        cleaned.pop("_seq", None)
        message_type = cleaned.get("type")
        if not isinstance(message_type, str):
            return

        if message_type in self._LATEST_ONLY_MESSAGES:
            with self._latest_messages_lock:
                self._latest_messages[message_type] = cleaned
            return

        self.message_queue.put(cleaned)

    def get_messages(self) -> list[dict[str, Any]]:
        """Return all queued messages received since the last call."""
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

        if latest_input is not None:
            messages.append(latest_input)
        if latest_snapshot is not None:
            messages.append(latest_snapshot)
        if latest_world is not None:
            messages.append(latest_world)

        return messages

    def _start_receive_loop(self) -> None:
        self.running = True
        self.receive_thread = threading.Thread(
            target=self._receive_loop, daemon=True, name="net-recv"
        )
        self.receive_thread.start()
        self._send_thread = threading.Thread(
            target=self._send_loop, daemon=True, name="net-send"
        )
        self._send_thread.start()

    def _start_udp_receive_loop(self) -> None:
        if not self.udp_socket:
            return
        self.udp_receive_thread = threading.Thread(
            target=self._udp_receive_loop, daemon=True, name="net-udp-recv"
        )
        self.udp_receive_thread.start()

    def _send_loop(self) -> None:
        """Dedicated send thread – drains the send queue without touching the game loop."""
        while self.running and self.connected:
            try:
                data = self._send_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            # Take a local reference so the socket cannot be set to None mid-send.
            sock = self.socket
            if sock is None:
                break
            try:
                sock.sendall(data)
            except (socket.error, BrokenPipeError, OSError) as exc:
                self.last_error = str(exc)
                self.connected = False
                break

    def _receive_loop(self) -> None:
        while self.running and self.connected and self.socket:
            try:
                length_bytes = self._recv_exact(4)
                if not length_bytes:
                    break

                length = int.from_bytes(length_bytes, "big")
                # Guard: reject absurd or empty lengths to prevent OOM / crash.
                if length <= 0 or length > MAX_MESSAGE_BYTES:
                    self.last_error = f"Rejected message with invalid length: {length}"
                    break

                payload = self._recv_exact(length)
                if not payload:
                    break

                message = json.loads(payload.decode("utf-8"))
                if isinstance(message, dict):
                    self._queue_message(message, via_udp=False)
            except (socket.error, OSError, json.JSONDecodeError) as exc:
                self.last_error = str(exc)
                break

        self.connected = False
        self.running = False

    def _udp_receive_loop(self) -> None:
        while self.running and self.connected and self.udp_socket:
            try:
                payload, address = self.udp_socket.recvfrom(MAX_UDP_MESSAGE_BYTES + 1024)
            except socket.timeout:
                continue
            except (socket.error, OSError):
                break

            if len(payload) > MAX_UDP_MESSAGE_BYTES:
                continue

            try:
                message = json.loads(payload.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

            if not isinstance(message, dict):
                continue

            message_type = message.get("type")
            if message_type == UDP_HANDSHAKE_TYPE:
                if self.is_host and self._can_accept_udp_peer(address):
                    self._set_udp_peer(address)
                    self._send_udp_control(UDP_READY_TYPE, address=address)
                continue
            if message_type == UDP_READY_TYPE:
                if not self.is_host and self._can_accept_udp_peer(address):
                    self._set_udp_peer(address)
                continue

            if not self._accept_udp_payload_sender(address):
                continue
            if self.udp_peer_address is None:
                self._set_udp_peer(address)

            self._queue_message(message, via_udp=True)

        self.udp_connected = False

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
        self.udp_connected = False
        self.udp_peer_address = None
        # Drain the send queue so the send thread can exit cleanly.
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except queue.Empty:
                break
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except OSError:
                pass
            self.udp_socket = None
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
        if self.udp_receive_thread and self.udp_receive_thread.is_alive():
            self.udp_receive_thread.join(timeout=1.0)
        if self._send_thread and self._send_thread.is_alive():
            self._send_thread.join(timeout=1.0)
        self._udp_last_recv_seq.clear()
        with self._latest_messages_lock:
            self._latest_messages.clear()


class NetworkHost(NetworkManager):
    """Host-side connection manager."""

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

    def start_hosting(self, advertised_name: str | None = None) -> bool:
        """Start listening for a LAN client without blocking the UI thread."""
        try:
            if advertised_name:
                self.advertised_name = advertised_name
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", self.port))
            self.server_socket.listen(1)
            self.server_socket.setblocking(False)
            # UDP is an optimization path; hosting should still work with TCP
            # even if this socket cannot be created.
            self._start_game_udp_socket()
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
            if self.udp_socket:
                try:
                    self.udp_socket.close()
                except OSError:
                    pass
                self.udp_socket = None
            self._stop_discovery_responder()
            return False

    def poll_connection(self) -> bool:
        """Accept a client if one is waiting."""
        if self.connected:
            return True
        if not self.server_socket or not self.listening:
            return False

        try:
            client_socket, addr = self.server_socket.accept()
        except BlockingIOError:
            return False
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            return False

        # Disable Nagle's algorithm so small game packets (input/snapshot) are
        # delivered immediately instead of being buffered by the OS.
        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client_socket.settimeout(0.25)
        self.socket = client_socket
        self.peer_address = addr
        self.connected = True
        self.last_error = None
        self._start_receive_loop()
        self._start_udp_receive_loop()
        return True

    def _start_game_udp_socket(self) -> bool:
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp_socket.bind(("0.0.0.0", self.port + GAME_UDP_PORT_OFFSET))
            udp_socket.settimeout(0.25)
            self.udp_socket = udp_socket
            self.udp_peer_address = None
            self.udp_connected = False
            return True
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            if self.udp_socket:
                try:
                    self.udp_socket.close()
                except OSError:
                    pass
                self.udp_socket = None
            return False

    def wait_for_connection(self, timeout: float = 30.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.poll_connection():
                return True
            time.sleep(0.05)
        return False

    def try_upnp_mapping(self) -> Optional[str]:
        """Attempt an automatic UPnP/IGD port mapping for internet play.

        Returns the router-reported external IP on success, or ``None`` when
        UPnP is unavailable, the router rejected the request, or the optional
        ``miniupnpc`` package is not installed.

        Install with: ``pip install miniupnpc``
        """
        try:
            import miniupnpc  # optional dependency
        except ImportError:
            return None

        try:
            upnp = miniupnpc.UPnP()
            upnp.discoverdelay = 300
            if upnp.discover() == 0:
                return None
            upnp.selectigd()
            result = upnp.addportmapping(
                self.port, "TCP", upnp.lanaddr, self.port, "Grid Survival", ""
            )
            if result:
                self._upnp_handle = upnp
                return upnp.externalipaddress()
        except Exception:
            pass
        return None

    def remove_upnp_mapping(self) -> None:
        """Remove the UPnP mapping created by :meth:`try_upnp_mapping`."""
        upnp = getattr(self, "_upnp_handle", None)
        if upnp is None:
            return
        try:
            upnp.deleteportmapping(self.port, "TCP")
        except Exception:
            pass
        self._upnp_handle = None

    def disconnect(self) -> None:
        self.remove_upnp_mapping()
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
            # Disable Nagle's algorithm for immediate delivery of small packets.
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            client.settimeout(0.25)
            self.socket = client
            self.peer_address = (host, port)
            self.connected = True
            self.last_error = None

            # UDP lane for high-frequency gameplay packets.
            self._start_client_udp_channel(host, port)

            self._start_receive_loop()
            self._start_udp_receive_loop()
            self._maybe_send_udp_hello()
            return True
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            self.connected = False
            if self.udp_socket:
                try:
                    self.udp_socket.close()
                except OSError:
                    pass
                self.udp_socket = None
            if self.socket:
                try:
                    self.socket.close()
                except OSError:
                    pass
                self.socket = None
            return False

    def _start_client_udp_channel(self, host: str, port: int) -> bool:
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp_socket.bind(("0.0.0.0", 0))
            udp_socket.settimeout(0.25)
            self.udp_socket = udp_socket
            self.udp_peer_address = (host, port + GAME_UDP_PORT_OFFSET)
            self.udp_connected = False
            self._udp_last_recv_seq.clear()
            return True
        except (socket.error, OSError):
            if self.udp_socket:
                try:
                    self.udp_socket.close()
                except OSError:
                    pass
                self.udp_socket = None
            self.udp_peer_address = None
            self.udp_connected = False
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


def get_public_ip(timeout: float = 5.0) -> Optional[str]:
    """Return the machine's public IPv4 address by querying an external service.

    Uses only the stdlib ``urllib`` package — no extra dependencies.
    Returns ``None`` when offline or when every service times out.
    Call this from a background thread so the UI stays responsive.
    """
    import urllib.request

    _SERVICES = [
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://icanhazip.com",
    ]
    for url in _SERVICES:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                ip = resp.read().decode("utf-8", errors="ignore").strip()
            # Basic sanity-check: four numeric octets.
            parts = ip.split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                return ip
        except Exception:
            continue
    return None
