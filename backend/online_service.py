from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None


def _load_repo_env_if_present() -> None:
    """Load local .env files for the desktop client without overriding explicit env vars."""
    if load_dotenv is None:
        return

    repo_root = Path(__file__).resolve().parents[1]
    candidates = [
        repo_root / ".env",
        repo_root / "backend" / ".env",
    ]
    for candidate in candidates:
        try:
            if candidate.exists():
                load_dotenv(candidate, override=False)
        except Exception:
            continue


@dataclass(frozen=True)
class OnlineServiceConfig:
    base_url: str
    timeout_seconds: float = 6.0
    api_key: str | None = None


class OnlineService:
    """Small control-plane HTTP client for internet lobby/queue APIs."""

    def __init__(self, config: OnlineServiceConfig):
        base = str(config.base_url or "").strip().rstrip("/")
        if not base:
            raise ValueError("OnlineService requires a non-empty base_url")
        self._base_url = base
        self._timeout = max(1.0, float(config.timeout_seconds))
        self._api_key = (config.api_key or "").strip() or None

    @classmethod
    def from_env(cls) -> "OnlineService":
        _load_repo_env_if_present()
        base_url = (
            os.getenv("GRID_SURVIVAL_ONLINE_API")
            or os.getenv("GRID_SURVIVAL_CONTROL_PLANE_URL")
            or "http://127.0.0.1:8010"
        )
        timeout_text = os.getenv("GRID_SURVIVAL_ONLINE_TIMEOUT", "6")
        api_key = os.getenv("GRID_SURVIVAL_ONLINE_API_KEY")
        try:
            timeout = float(timeout_text)
        except (TypeError, ValueError):
            timeout = 6.0
        debug_value = str(os.getenv("GRID_SURVIVAL_DEBUG_ONLINE", "")).strip().lower()
        if debug_value in {"1", "true", "yes", "on"}:
            try:
                print(f"[DEBUG] OnlineService.from_env -> base_url={base_url} api_key_set={bool(api_key)}")
            except Exception:
                pass
        return cls(OnlineServiceConfig(base_url=base_url, timeout_seconds=timeout, api_key=api_key))

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._api_key:
            headers["X-API-Key"] = self._api_key
        return headers

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                if not raw:
                    return {"ok": True}
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
                return {"ok": True, "data": data}
        except urllib.error.HTTPError as exc:
            try:
                raw = exc.read().decode("utf-8", errors="replace")
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {}
            message = parsed.get("error") if isinstance(parsed, dict) else None
            return {
                "ok": False,
                "error": str(message or f"http {exc.code}"),
                "status": int(exc.code),
            }
        except urllib.error.URLError as exc:
            return {"ok": False, "error": f"network: {exc.reason}"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def create_lobby(
        self,
        *,
        player_name: str,
        mode: str,
        target_score: int,
        map_pool: list[int],
        region: str,
        max_players: int,
        rating: int,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/internet/lobbies/create",
            {
                "player": str(player_name),
                "mode": str(mode),
                "target_score": int(target_score),
                "map_pool": [int(x) for x in map_pool],
                "region": str(region),
                "max_players": int(max_players),
                "rating": int(rating),
            },
        )

    def join_lobby(self, *, player_name: str, lobby_code: str, rating: int = 1000) -> dict[str, Any]:
        return self._request(
            "POST",
            "/internet/lobbies/join",
            {
                "player": str(player_name),
                "lobby_code": str(lobby_code).upper(),
                "rating": int(rating),
            },
        )

    def set_ready(self, *, player_name: str, lobby_code: str, ready: bool) -> dict[str, Any]:
        return self._request(
            "POST",
            "/internet/lobbies/ready",
            {
                "player": str(player_name),
                "lobby_code": str(lobby_code).upper(),
                "ready": bool(ready),
            },
        )

    def queue(
        self,
        *,
        player_name: str,
        lobby_code: str,
        region: str,
        rating: int,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/internet/queue/enqueue",
            {
                "player": str(player_name),
                "lobby_code": str(lobby_code).upper(),
                "region": str(region),
                "rating": int(rating),
            },
        )

    def dequeue(self, *, player_name: str, lobby_code: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/internet/queue/dequeue",
            {
                "player": str(player_name),
                "lobby_code": str(lobby_code).upper(),
            },
        )

    def poll_or_ws_updates(self, *, player_name: str) -> dict[str, Any]:
        query = urllib.parse.urlencode({"player": str(player_name)})
        return self._request("GET", f"/internet/updates?{query}")
