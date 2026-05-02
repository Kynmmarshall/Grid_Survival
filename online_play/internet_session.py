"""Internet session client built on top of the UDP client transport."""

from __future__ import annotations

import os
import re
import random
import time
import urllib.parse

from .session import DEFAULT_PORT, NetworkClient


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
        parsed = self._parse_endpoint(endpoint)
        if parsed is None:
            self.last_error = f"Invalid match endpoint: {endpoint}"
            return False

        host, port = parsed
        host = self._normalize_match_host(host)
        try:
            print(f"[DEBUG] InternetSessionClient.connect_to_match -> endpoint={endpoint} parsed={host}:{port} token_set={bool(token)} player={player_name}")
        except Exception:
            pass

        connected = False
        connect_attempts = 3
        for attempt in range(1, connect_attempts + 1):
            if self.connect_to_host(host, port):
                connected = True
                break
            try:
                print(
                    f"[DEBUG] connect_to_host attempt {attempt}/{connect_attempts} failed -> last_error={self.last_error}"
                )
            except Exception:
                pass
            if attempt < connect_attempts:
                time.sleep(0.35)

        if not connected:
            return False

        self.match_endpoint = str(endpoint)
        self.match_token = str(token)
        self.player_name = str(player_name)
        self._last_host = host
        self._last_port = int(port)
        self._last_auth_ok = False

        if not self.send_message(
            "internet_auth",
            token=self.match_token,
            player=self.player_name,
            resume=False,
        ):
            self.last_error = "Failed to send internet_auth"
            self.disconnect()
            return False

        started = time.time()
        while time.time() - started < 2.5:
            for message in self.get_messages():
                if message.get("type") == "internet_auth_ok":
                    self.session_id = str(message.get("session_id", "")) or None
                    self._last_auth_ok = True
                    return True
                if message.get("type") == "internet_auth_error":
                    self.last_error = str(message.get("error", "auth rejected"))
                    self.disconnect()
                    return False
            time.sleep(0.02)

        self.request_resync("initial_join")
        return True

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
