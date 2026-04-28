"""Session-level helpers that sit above the UDP transport layer."""

from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass
from typing import Optional

from .transport import DEFAULT_PORT, NetworkManager, UdpClientTransport, UdpHostTransport


DISCOVERY_PORT = 5556
DISCOVERY_MAGIC = "grid_survival_lan_v1"
DISCOVERY_HOST_MAX_AGE = 4.0


@dataclass
class DiscoveredHost:
    host_name: str
    machine_name: str
    address: str
    port: int
    last_seen: float


class NetworkHost(UdpHostTransport):
    """Session-facing host with LAN discovery and optional UPnP mapping."""

    def __init__(self, port: int = DEFAULT_PORT):
        super().__init__(port=port)
        self.advertised_name = "Host"
        self.machine_name = socket.gethostname()
        self.discovery_socket: Optional[socket.socket] = None
        self.discovery_thread: Optional[threading.Thread] = None
        self.discovery_running = False

    def start_hosting(self, advertised_name: str | None = None) -> bool:
        if advertised_name:
            self.advertised_name = advertised_name
        if not super().start_hosting():
            return False
        try:
            self._start_discovery_responder()
        except (socket.error, OSError) as exc:
            self.last_error = str(exc)
            super().disconnect()
            self.listening = False
            return False
        return True

    def try_upnp_mapping(self) -> Optional[str]:
        try:
            import miniupnpc
        except ImportError:
            return None
        try:
            upnp = miniupnpc.UPnP()
            upnp.discoverdelay = 300
            if upnp.discover() == 0:
                return None
            upnp.selectigd()
            result = upnp.addportmapping(
                self.port,
                "UDP",
                upnp.lanaddr,
                self.port,
                "Grid Survival UDP",
                "",
            )
            if result:
                self._upnp_handle = upnp
                return upnp.externalipaddress()
        except Exception:
            pass
        return None

    def remove_upnp_mapping(self) -> None:
        upnp = getattr(self, "_upnp_handle", None)
        if upnp is None:
            return
        try:
            upnp.deleteportmapping(self.port, "UDP")
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


class NetworkClient(UdpClientTransport):
    """Session-facing client transport."""


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
            host_name = str(message.get("host_name", "Host"))
            machine_name = str(message.get("machine_name", addr[0]))
            identity = (machine_name.lower(), port)
            existing = self._hosts.get(identity)
            if existing is not None:
                existing.last_seen = now
                existing.host_name = host_name
                if existing.address.startswith("127.") and not addr[0].startswith("127."):
                    existing.address = addr[0]
                continue
            self._hosts[identity] = DiscoveredHost(
                host_name=host_name,
                machine_name=machine_name,
                address=addr[0],
                port=port,
                last_seen=now,
            )
        active_hosts = [
            host
            for host in self._hosts.values()
            if now - host.last_seen <= DISCOVERY_HOST_MAX_AGE
        ]
        self._hosts = {(host.machine_name.lower(), host.port): host for host in active_hosts}
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
    import urllib.request

    services = [
        "https://api.ipify.org",
        "https://checkip.amazonaws.com",
        "https://icanhazip.com",
    ]
    for url in services:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                ip = resp.read().decode("utf-8", errors="ignore").strip()
            parts = ip.split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                return ip
        except Exception:
            continue
    return None
