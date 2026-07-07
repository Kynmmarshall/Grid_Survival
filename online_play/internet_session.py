"""Internet session client built on top of the UDP client transport."""

from __future__ import annotations

import os
import re
import random
import time
import urllib.parse

from .session import DEFAULT_PORT, NetworkClient
from .log import get_logger
from .exceptions import InternetFallbackLAN


class InternetSessionClient(NetworkClient):
    """Internet match session client with reconnect and resync helpers."""

    def __init__(self):
        super().__init__()
        self.match_endpoint: str | None = None
        self.match_token: str | None = None
        self.player_name: str | None = None
        self.session_id: str | None = None
        self._last_host: str | None = None
        self._last_port: int = DEFAULT_PORT
        self._last_auth_ok = False
        self._last_resync_request_at = 0.0
        self._logger = get_logger("internet_session")

    @staticmethod
    def _parse_endpoint(endpoint: str) -> tuple[str, int] | None:
        clean = str(endpoint or "").strip()
        if not clean:
            return None
        if "://" in clean:
            scheme, rest = clean.split("://", 1)
            if scheme.lower().strip() not in {"udp", "ws", "wss"}:
                return None
            clean = rest
        if "/" in clean:
            clean = clean.split("/", 1)[0]
        if clean.startswith("["):
            return None

        match = re.match(r"^(?P<host>[^:]+)(:(?P<port>\d+))?$", clean)
        if not match:
            return None
        host = str(match.group("host") or "").strip()
        port_text = match.group("port")
        if not host:
            return None
        port = DEFAULT_PORT
        if port_text:
            try:
                port = int(port_text)
            except (TypeError, ValueError):
                return None
            if not (1 <= port <= 65535):
                return None
        return host, port

    @staticmethod
    def _fallback_public_host() -> str | None:
        raw = (
            os.getenv("GRID_SURVIVAL_ONLINE_API")
            or os.getenv("GRID_SURVIVAL_CONTROL_PLANE_URL")
            or ""
        ).strip()
        if not raw:
            return None
        parsed = urllib.parse.urlparse(raw if "://" in raw else f"http://{raw}")
        host = (parsed.hostname or "").strip()
        return host or None

    @staticmethod
    def _normalize_match_host(host: str) -> str:
        clean = str(host or "").strip()
        if clean in {"0.0.0.0", "127.0.0.1", "localhost", "::1", ""}:
            return InternetSessionClient._fallback_public_host() or clean
        return clean

    def connect_to_match(self, *, endpoint: str, token: str, player_name: str) -> bool:
        print(f"[ONLINE] connect_to_match: endpoint={endpoint!r} player={player_name!r}", flush=True)
        parsed = self._parse_endpoint(endpoint)
        if parsed is None:
            self.last_error = f"Invalid match endpoint: {endpoint}"
            print(f"[ONLINE] connect_to_match: FAILED - {self.last_error}", flush=True)
            return False

        host, port = parsed
        host = self._normalize_match_host(host)
        print(f"[ONLINE] connect_to_match: resolved target {host}:{port}", flush=True)

        # Store for later use
        self.match_endpoint = str(endpoint)
        self.match_token = str(token)
        self.player_name = str(player_name)
        self._last_host = host
        self._last_port = int(port)
        self._last_auth_ok = False

        try:
            self._logger.debug(
                "connect_to_match -> endpoint=%s parsed=%s token_set=%s player=%s",
                endpoint,
                f"{host}:{port}",
                bool(token),
                player_name,
            )
        except Exception:
            pass

        # === PHASE 1: Try TCP handshake (most reliable through firewalls) ===
        # Note: this branch is currently unreachable in practice -- nothing
        # ever sets self.transport on this class, so hasattr() is always
        # False. Left as-is (not this task's scope to fix), but logged so
        # it's visible if that ever changes.
        tcp_auth_ok = False
        try:
            if hasattr(self, 'transport') and hasattr(self.transport, '_tcp_handshake'):
                print("[ONLINE] connect_to_match: attempting TCP handshake...", flush=True)
                if self.transport._tcp_handshake(host, port, token, player_name):
                    self.session_id = self.transport.session_id
                    self._last_auth_ok = True
                    tcp_auth_ok = True
                    print("[ONLINE] connect_to_match: TCP handshake OK", flush=True)
        except Exception as exc:
            print(f"[ONLINE] connect_to_match: TCP handshake attempt raised {exc}", flush=True)

        if tcp_auth_ok:
            if self.connect_to_host(host, port):
                return True

        # === PHASE 2: Try clean UDP hello from scratch ===
        print(f"[ONLINE] connect_to_match: attempting UDP hello to {host}:{port} (up to 3 tries)...", flush=True)
        connected = False
        for attempt in range(1, 4):
            print(f"[ONLINE] connect_to_match: UDP hello attempt {attempt}/3...", flush=True)
            if self.connect_to_host(host, port):
                connected = True
                print(f"[ONLINE] connect_to_match: UDP hello succeeded on attempt {attempt}", flush=True)
                break
            print(f"[ONLINE] connect_to_match: UDP hello attempt {attempt} failed: {self.last_error}", flush=True)
            if attempt < 3:
                time.sleep(0.35)

        if not connected:
            # Check if connection was refused (LAN fallback case)
            if self.last_error is not None:
                lower = str(self.last_error).lower()
                if any(x in lower for x in ["econnrefused", "connection refused", "winerror 10061", "refused"]):
                    self._logger.warning("Internet connection refused; triggering LAN fallback")
                    print("[ONLINE] connect_to_match: connection refused, falling back to LAN", flush=True)
                    raise InternetFallbackLAN("Internet connect refused; fallback to LAN")

            self.last_error = "Failed to connect via TCP or UDP"
            print(f"[ONLINE] connect_to_match: FAILED - {self.last_error}", flush=True)
            return False

        # === PHASE 3: Send internet_auth and wait for confirmation ===
        print("[ONLINE] connect_to_match: sending internet_auth, waiting for server response...", flush=True)
        if not self.send_message(
            "internet_auth",
            token=token,
            player=player_name,
            resume=False,
        ):
            self.last_error = "Failed to send internet_auth"
            print(f"[ONLINE] connect_to_match: FAILED - {self.last_error}", flush=True)
            self.disconnect()
            return False

        started = time.time()
        while time.time() - started < 5.0:
            for message in self.get_messages():
                if message.get("type") == "internet_auth_ok":
                    self.session_id = str(message.get("session_id", "")) or None
                    self._last_auth_ok = True
                    print(f"[ONLINE] connect_to_match: internet_auth_ok, session_id={self.session_id}", flush=True)
                    return True
                if message.get("type") == "internet_auth_error":
                    self.last_error = str(message.get("error", "auth rejected"))
                    print(f"[ONLINE] connect_to_match: FAILED - server rejected auth: {self.last_error}", flush=True)
                    self.disconnect()
                    return False
            time.sleep(0.02)

        self.last_error = "Timed out waiting for internet_auth_ok"
        print(f"[ONLINE] connect_to_match: FAILED - {self.last_error}", flush=True)
        self.disconnect()
        return False

    def request_resync(self, reason: str = "manual") -> bool:
        now = time.time()
        if now - self._last_resync_request_at < 0.35:
            return False
        self._last_resync_request_at = now
        return self.send_message(
            "resync_request",
            reason=str(reason),
            session_id=self.session_id,
            player=self.player_name,
        )

    def reconnect(self, attempts: int = 4) -> bool:
        if not self._last_host or not self.match_token or not self.player_name:
            self.last_error = "Missing session data for reconnect"
            return False

        max_attempts = max(1, int(attempts))
        for attempt in range(max_attempts):
            # Try the TCP handshake first, same as the initial connect_to_match
            # (PHASE 1) -- some networks/firewalls only ever let the TCP path
            # through, so a UDP-only reconnect can silently never reach the
            # server even though the original connection worked.
            tcp_auth_ok = False
            try:
                if hasattr(self, "transport") and hasattr(self.transport, "_tcp_handshake"):
                    if self.transport._tcp_handshake(
                        self._last_host, self._last_port, self.match_token, self.player_name
                    ):
                        self.session_id = self.transport.session_id
                        tcp_auth_ok = True
            except Exception:
                pass

            if tcp_auth_ok and self.connect_to_host(self._last_host, self._last_port):
                self.request_resync("reconnect")
                self._last_auth_ok = True
                return True

            if self.connect_to_host(self._last_host, self._last_port):
                auth_sent = self.send_message(
                    "internet_auth",
                    token=self.match_token,
                    player=self.player_name,
                    resume=True,
                    session_id=self.session_id,
                )
                if auth_sent:
                    self.request_resync("reconnect")
                    self._last_auth_ok = True
                    return True
            if attempt < max_attempts - 1:
                base_delay = min(4.0, 0.35 * (2 ** attempt))
                jitter = random.uniform(0.0, min(0.75, base_delay * 0.4))
                time.sleep(base_delay + jitter)
        self.last_error = self.last_error or "Reconnect failed"
        return False
