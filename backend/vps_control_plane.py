from __future__ import annotations

import json
import os
import random
import string
import signal
import threading
import time
import traceback
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from character_manager import available_characters
from backend.vps_match_server import MatchServerManager
from backend.match_daemon import run_daemon_from_manager


HOST = os.getenv("GRID_SURVIVAL_CONTROL_HOST", "0.0.0.0")
PORT = int(os.getenv("GRID_SURVIVAL_CONTROL_PORT", "8010"))
API_KEY = (os.getenv("GRID_SURVIVAL_ONLINE_API_KEY") or "").strip() or None
MATCH_BOT_FILL_SECONDS = max(1.0, float(os.getenv("GRID_SURVIVAL_MATCH_BOT_FILL_SECONDS", "10")))
MATCH_SERVER_MANAGER = MatchServerManager.from_env()


def _rand_code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(max(4, length)))


@dataclass
class Lobby:
    code: str
    owner: str
    mode: str
    target_score: int
    map_pool: list[int]
    region: str
    max_players: int
    created_at: float
    members: dict[str, dict[str, Any]] = field(default_factory=dict)
    queued: bool = False
    pending_match: dict[str, Any] | None = None
    match_config: dict[str, Any] | None = None


class ControlPlaneState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lobbies: dict[str, Lobby] = {}
        self.player_lobby: dict[str, str] = {}
        self.queue: list[dict[str, Any]] = []
        self.player_updates: dict[str, list[dict[str, Any]]] = {}
        self.match_serial = 0

    def _push_update(self, player: str, event: dict[str, Any]) -> None:
        if player not in self.player_updates:
            self.player_updates[player] = []
        self.player_updates[player].append(event)

    def _queue_entry_for_lobby(self, lobby_code: str) -> dict[str, Any] | None:
        for item in self.queue:
            if item.get("lobby_code") == lobby_code:
                return item
        return None

    def _remove_queue_entry(self, lobby_code: str) -> None:
        self.queue = [item for item in self.queue if item.get("lobby_code") != lobby_code]

    def create_lobby(self, payload: dict[str, Any]) -> dict[str, Any]:
        player = str(payload.get("player", "")).strip()
        if not player:
            return {"ok": False, "error": "missing player"}

        mode = str(payload.get("mode") or "ranked")
        target_score = max(1, int(payload.get("target_score", 3)))
        map_pool_raw = payload.get("map_pool") or [1]
        map_pool = [int(x) for x in map_pool_raw if isinstance(x, (int, float, str))]
        map_pool = map_pool or [1]
        region = str(payload.get("region") or "global").lower()
        max_players = max(2, min(4, int(payload.get("max_players", 2))))
        rating = int(payload.get("rating", 1000))
        character_name = str(payload.get("character_name", "Caveman")).strip() or "Caveman"

        with self.lock:
            if player in self.player_lobby:
                old_code = self.player_lobby[player]
                old_lobby = self.lobbies.get(old_code)
                if old_lobby:
                    old_lobby.members.pop(player, None)

            code = _rand_code(6)
            while code in self.lobbies:
                code = _rand_code(6)

            lobby = Lobby(
                code=code,
                owner=player,
                mode=mode,
                target_score=target_score,
                map_pool=map_pool,
                region=region,
                max_players=max_players,
                created_at=time.time(),
            )
            lobby.members[player] = {
                "ready": False,
                "rating": rating,
                "character": character_name,
                "joined_at": time.time(),
            }
            self.lobbies[code] = lobby
            self.player_lobby[player] = code

            return {"ok": True, "lobby": self._serialize_lobby(lobby)}

    def join_lobby(self, payload: dict[str, Any]) -> dict[str, Any]:
        player = str(payload.get("player", "")).strip()
        code = str(payload.get("lobby_code", "")).strip().upper()
        rating = int(payload.get("rating", 1000))
        character_name = str(payload.get("character_name", "Caveman")).strip() or "Caveman"
        if not player or not code:
            return {"ok": False, "error": "missing player or lobby_code"}

        with self.lock:
            lobby = self.lobbies.get(code)
            if lobby is None:
                return {"ok": False, "error": "lobby not found"}
            if len(lobby.members) >= lobby.max_players and player not in lobby.members:
                return {"ok": False, "error": "lobby full"}

            lobby.members[player] = {
                "ready": False,
                "rating": rating,
                "character": character_name,
                "joined_at": time.time(),
            }
            self.player_lobby[player] = code

            for member in lobby.members:
                self._push_update(member, {"type": "lobby_updated", "lobby": self._serialize_lobby(lobby)})

            return {"ok": True, "lobby": self._serialize_lobby(lobby)}

    def set_ready(self, payload: dict[str, Any]) -> dict[str, Any]:
        player = str(payload.get("player", "")).strip()
        code = str(payload.get("lobby_code", "")).strip().upper()
        ready = bool(payload.get("ready", False))
        if not player or not code:
            return {"ok": False, "error": "missing player or lobby_code"}

        with self.lock:
            lobby = self.lobbies.get(code)
            if lobby is None or player not in lobby.members:
                return {"ok": False, "error": "not in lobby"}
            lobby.members[player]["ready"] = ready
            for member in lobby.members:
                self._push_update(member, {"type": "lobby_updated", "lobby": self._serialize_lobby(lobby)})
            return {"ok": True, "lobby": self._serialize_lobby(lobby)}

    def set_character(self, payload: dict[str, Any]) -> dict[str, Any]:
        player = str(payload.get("player", "")).strip()
        code = str(payload.get("lobby_code", "")).strip().upper()
        character = str(payload.get("character", "")).strip()
        if not player or not code or not character:
            return {"ok": False, "error": "missing player, lobby_code or character"}

        with self.lock:
            lobby = self.lobbies.get(code)
            if lobby is None or player not in lobby.members:
                return {"ok": False, "error": "not in lobby"}

            used = {
                str(member.get("character", "")).strip().lower()
                for name, member in lobby.members.items()
                if name != player
            }
            if character.lower() in used:
                return {"ok": False, "error": f"{character} is already taken"}

            lobby.members[player]["character"] = character
            pending = self._maybe_finalize_lobby_match(lobby)
            for member in lobby.members:
                self._push_update(member, {"type": "lobby_updated", "lobby": self._serialize_lobby(lobby)})
            payload_out: dict[str, Any] = {"ok": True, "lobby": self._serialize_lobby(lobby)}
            if pending is not None:
                payload_out["match"] = pending
            return payload_out

    def enqueue(self, payload: dict[str, Any]) -> dict[str, Any]:
        player = str(payload.get("player", "")).strip()
        code = str(payload.get("lobby_code", "")).strip().upper()
        region = str(payload.get("region") or "global").lower()
        rating = int(payload.get("rating", 1000))
        if not player or not code:
            return {"ok": False, "error": "missing player or lobby_code"}

        with self.lock:
            lobby = self.lobbies.get(code)
            if lobby is None or player not in lobby.members:
                return {"ok": False, "error": "not in lobby"}
            if not all(bool(member.get("ready")) for member in lobby.members.values()):
                return {"ok": False, "error": "all members must be ready"}

            existing = self._queue_entry_for_lobby(code)
            if existing is None:
                self.queue.append(
                    {
                        "lobby_code": code,
                        "region": region,
                        "rating": rating,
                        "queued_at": time.time(),
                    }
                )
            lobby.queued = True
            for member in lobby.members:
                self._push_update(member, {"type": "queue_joined", "lobby_code": code})
            return {"ok": True, "lobby": self._serialize_lobby(lobby)}

    def dequeue(self, payload: dict[str, Any]) -> dict[str, Any]:
        player = str(payload.get("player", "")).strip()
        code = str(payload.get("lobby_code", "")).strip().upper()
        if not player or not code:
            return {"ok": False, "error": "missing player or lobby_code"}

        with self.lock:
            lobby = self.lobbies.get(code)
            if lobby is None:
                return {"ok": False, "error": "lobby not found"}
            self._remove_queue_entry(code)
            lobby.queued = False
            for member in lobby.members:
                self._push_update(member, {"type": "queue_left", "lobby_code": code})
            return {"ok": True, "lobby": self._serialize_lobby(lobby)}

    def poll_updates(self, player: str) -> dict[str, Any]:
        clean = str(player or "").strip()
        if not clean:
            return {"ok": False, "error": "missing player"}

        with self.lock:
            events = self.player_updates.get(clean, [])
            self.player_updates[clean] = []
            lobby_code = self.player_lobby.get(clean)
            lobby = self.lobbies.get(lobby_code) if lobby_code else None
            return {
                "ok": True,
                "events": events,
                "lobby": self._serialize_lobby(lobby) if lobby else None,
            }

    def matchmaking_tick(self) -> None:
        with self.lock:
            if not self.queue:
                return

            # Group queue by mode/region/max_players for deterministic matchmaking.
            groups: dict[tuple[str, str, int], list[dict[str, Any]]] = {}
            for entry in self.queue:
                lobby = self.lobbies.get(str(entry.get("lobby_code", "")))
                if not lobby:
                    continue
                key = (lobby.mode, lobby.region, lobby.max_players)
                groups.setdefault(key, []).append(entry)

            consumed: set[str] = set()
            for key, entries in groups.items():
                entries.sort(key=lambda e: float(e.get("queued_at", 0.0)))
                mode, region, max_players = key
                _ = (mode, region)

                i = 0
                while i < len(entries):
                    if entries[i]["lobby_code"] in consumed:
                        i += 1
                        continue

                    batch = [entries[i]]
                    target_players = max_players
                    humans = self._lobby_member_count(entries[i]["lobby_code"])
                    wait_secs = max(0.0, time.time() - float(entries[i].get("queued_at", time.time())))

                    j = i + 1
                    while j < len(entries) and humans < target_players:
                        next_code = entries[j]["lobby_code"]
                        if next_code in consumed:
                            j += 1
                            continue
                        next_humans = self._lobby_member_count(next_code)
                        if humans + next_humans <= target_players:
                            batch.append(entries[j])
                            humans += next_humans
                        j += 1

                    if humans < target_players and wait_secs < MATCH_BOT_FILL_SECONDS:
                        i += 1
                        continue

                    bot_count = max(0, target_players - humans)
                    self._emit_match_found(
                        batch,
                        target_players=target_players,
                        bot_count=bot_count,
                        pending_config=True,
                    )
                    for item in batch:
                        consumed.add(str(item["lobby_code"]))
                    i += 1

            if consumed:
                self.queue = [entry for entry in self.queue if str(entry.get("lobby_code")) not in consumed]

    def _lobby_member_count(self, code: str) -> int:
        lobby = self.lobbies.get(str(code))
        if lobby is None:
            return 0
        return len(lobby.members)

    def _emit_match_found(
        self,
        queue_entries: list[dict[str, Any]],
        *,
        target_players: int,
        bot_count: int,
        pending_config: bool = False,
        match_config: dict[str, Any] | None = None,
        match_id: str | None = None,
    ) -> dict[str, Any] | None:
        if match_id is None:
            self.match_serial += 1
            match_id = f"match-{self.match_serial:08d}"
        players: list[dict[str, Any]] = []

        lobbies: list[Lobby] = []
        for entry in queue_entries:
            lobby = self.lobbies.get(str(entry.get("lobby_code")))
            if lobby:
                lobbies.append(lobby)

        if not lobbies:
            return None

        base_lobby = lobbies[0]
        used_characters: set[str] = set()
        for lobby in lobbies:
            lobby.queued = False
            lobby.pending_match = {
                "match_id": match_id,
                "target_players": int(target_players),
                "bot_count": int(bot_count),
                "players": [],
            }
            for member_name, member in lobby.members.items():
                character = str(member.get("character", "")).strip()
                player_entry = {
                    "name": member_name,
                    "bot": False,
                "rating": int(member.get("rating", 1000)),
                "character": character if character else ("" if pending_config else "Caveman"),
                }
                if character:
                    used_characters.add(character.lower())
                players.append(player_entry)

        final_players = [dict(player) for player in players]
        if not pending_config:
            for idx in range(bot_count):
                profile = ["Diamond", "Master", "Apex"][idx % 3]
                bot_character = self._choose_bot_character(used_characters)
                used_characters.add(bot_character.lower())
                final_players.append({"name": f"BOT-{profile}-{idx + 1}", "bot": True, "profile": profile, "character": bot_character})

        if not pending_config:
            for player in final_players:
                if str(player.get("character", "")).strip():
                    continue
                player["character"] = str(player.get("profile", "Caveman")) if bool(player.get("bot")) else "Caveman"

        for lobby in lobbies:
            if lobby.pending_match is not None:
                lobby.pending_match["players"] = [dict(player) for player in final_players]

        match_payload = {
            "match_id": match_id,
            "mode": base_lobby.mode,
            "region": base_lobby.region,
            "target_score": base_lobby.target_score,
            "map_id": int(base_lobby.map_pool[0] if base_lobby.map_pool else 1),
            "players": final_players,
            "bot_filled": bot_count > 0,
            "bot_count": bot_count,
            "pending_config": bool(pending_config),
            "match_config": dict(match_config) if isinstance(match_config, dict) else None,
        }
        if not pending_config:
            match_payload["join"] = MATCH_SERVER_MANAGER.issue_assignment(
                match_id=match_id,
                payload={
                    "mode": match_payload["mode"],
                    "region": match_payload["region"],
                    "target_score": int(match_payload["target_score"]),
                    "map_id": int(match_payload["map_id"]),
                    "players": final_players,
                    "bot_count": int(bot_count),
                    "player_count": int(target_players),
                },
            )

        payload = {"type": "match_found", "match": match_payload}
        for lobby in lobbies:
            for member_name in lobby.members:
                self._push_update(member_name, payload)
        return match_payload

    def _choose_bot_character(self, used_characters: set[str]) -> str:
        pool = [name for name in available_characters() if name.lower() not in used_characters]
        if pool:
            return random.choice(pool)
        fallback_pool = available_characters()
        if fallback_pool:
            return random.choice(fallback_pool)
        return "Caveman"

    def set_match_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        player = str(payload.get("player", "")).strip()
        code = str(payload.get("lobby_code", "")).strip().upper()
        if not player or not code:
            return {"ok": False, "error": "missing player or lobby_code"}

        with self.lock:
            lobby = self.lobbies.get(code)
            if lobby is None or player not in lobby.members:
                return {"ok": False, "error": "not in lobby"}
            if lobby.owner != player:
                return {"ok": False, "error": "only the lobby owner can finalize match config"}
            if not isinstance(lobby.pending_match, dict):
                return {"ok": False, "error": "no pending match to finalize"}

            level_id = max(1, int(payload.get("level_id", lobby.map_pool[0] if lobby.map_pool else 1)))
            leader_character = str(payload.get("character", payload.get("leader_character", ""))).strip()

            if leader_character:
                lobby.members[player]["character"] = leader_character

            lobby.map_pool = [level_id]
            lobby.match_config = {
                "level_id": level_id,
                "target_score": int(lobby.target_score),
                "player_count": int(lobby.max_players),
                "leader_character": leader_character or str(lobby.members[player].get("character", "")).strip(),
            }

            pending = dict(lobby.pending_match)
            queue_entries = [{"lobby_code": code, "queued_at": time.time(), "region": lobby.region, "rating": int(lobby.members[player].get("rating", 1000))}]
            staged_match = self._emit_match_found(
                queue_entries,
                target_players=int(pending.get("target_players", lobby.max_players)),
                bot_count=int(pending.get("bot_count", 0)),
                pending_config=True,
                match_config=lobby.match_config,
                match_id=str(pending.get("match_id", "")) or None,
            )
            if staged_match is not None:
                lobby.pending_match["players"] = [dict(player) for player in staged_match.get("players", []) if isinstance(player, dict)]
            for member in lobby.members:
                self._push_update(member, {"type": "match_configured", "lobby": self._serialize_lobby(lobby), "match": staged_match})
            pending_match = self._maybe_finalize_lobby_match(lobby)
            if pending_match is not None:
                return {"ok": True, "match": pending_match, "lobby": self._serialize_lobby(lobby)}
            return {"ok": True, "match": staged_match, "lobby": self._serialize_lobby(lobby)}

    def _maybe_finalize_lobby_match(self, lobby: Lobby) -> dict[str, Any] | None:
        if not isinstance(lobby.pending_match, dict) or not isinstance(lobby.match_config, dict):
            return None

        all_selected = True
        for member in lobby.members.values():
            if not str(member.get("character", "")).strip():
                all_selected = False
                break
        if not all_selected:
            return None

        pending = dict(lobby.pending_match)
        queue_entries = [{"lobby_code": lobby.code, "queued_at": time.time(), "region": lobby.region, "rating": int(next(iter(lobby.members.values()), {}).get("rating", 1000))}]
        final_match = self._emit_match_found(
            queue_entries,
            target_players=int(pending.get("target_players", lobby.max_players)),
            bot_count=int(pending.get("bot_count", 0)),
            pending_config=False,
            match_config=lobby.match_config,
            match_id=str(pending.get("match_id", "")) or None,
        )
        lobby.pending_match = None
        lobby.match_config = None
        return final_match

    def _serialize_lobby(self, lobby: Lobby | None) -> dict[str, Any] | None:
        if lobby is None:
            return None
        return {
            "code": lobby.code,
            "owner": lobby.owner,
            "mode": lobby.mode,
            "target_score": lobby.target_score,
            "map_pool": list(lobby.map_pool),
            "region": lobby.region,
            "max_players": lobby.max_players,
            "queued": bool(lobby.queued),
            "pending_match": dict(lobby.pending_match) if isinstance(lobby.pending_match, dict) else None,
            "match_config": dict(lobby.match_config) if isinstance(lobby.match_config, dict) else None,
            "members": [
                {
                    "name": name,
                    "ready": bool(data.get("ready", False)),
                    "rating": int(data.get("rating", 1000)),
                    "character": str(data.get("character", "")).strip(),
                }
                for name, data in lobby.members.items()
            ],
        }


STATE = ControlPlaneState()


class ControlPlaneHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = "GridSurvivalControlPlane/0.1"

    def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _auth_ok(self) -> bool:
        if API_KEY is None:
            return True
        incoming = (self.headers.get("X-API-Key") or "").strip()
        return incoming == API_KEY

    def _json_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except (TypeError, ValueError):
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def do_GET(self) -> None:
        if not self._auth_ok():
            self._send(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return

        if self.path == "/health":
            self._send(HTTPStatus.OK, {"ok": True, "service": "control-plane"})
            return

        if self.path.startswith("/internet/updates"):
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = {}
            for pair in query.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[k] = v
            player = params.get("player", "")
            payload = STATE.poll_updates(player)
            status = HTTPStatus.OK if payload.get("ok") else HTTPStatus.BAD_REQUEST
            self._send(status, payload)
            return

        self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        if not self._auth_ok():
            self._send(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "unauthorized"})
            return

        payload = self._json_body()
        route = self.path

        if route == "/internet/lobbies/create":
            out = STATE.create_lobby(payload)
        elif route == "/internet/lobbies/join":
            out = STATE.join_lobby(payload)
        elif route == "/internet/lobbies/ready":
            out = STATE.set_ready(payload)
        elif route == "/internet/lobbies/character":
            out = STATE.set_character(payload)
        elif route == "/internet/lobbies/config":
            out = STATE.set_match_config(payload)
        elif route == "/internet/queue/enqueue":
            out = STATE.enqueue(payload)
        elif route == "/internet/queue/dequeue":
            out = STATE.dequeue(payload)
        else:
            self._send(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return

        status = HTTPStatus.OK if out.get("ok") else HTTPStatus.BAD_REQUEST
        self._send(status, out)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def _matchmaking_loop() -> None:
    while True:
        try:
            STATE.matchmaking_tick()
        except Exception:
            traceback.print_exc()
        time.sleep(1.0)


def _run_match_daemon() -> None:
    while True:
        try:
            print("[DEBUG] Starting match daemon thread", flush=True)
            run_daemon_from_manager(MATCH_SERVER_MANAGER)
            # Defensive: if run_daemon_from_manager returns unexpectedly,
            # restart shortly to keep UDP matchmaking available.
            print("[WARN] Match daemon exited unexpectedly; restarting", flush=True)
        except Exception:
            traceback.print_exc()
            print("[WARN] Match daemon crashed; restarting", flush=True)
        time.sleep(1.0)


def run_server() -> None:
    stop_event = threading.Event()

    def _request_stop(*_args: object) -> None:
        stop_event.set()
        try:
            server.shutdown()
        except Exception:
            pass

    threading.Thread(target=_matchmaking_loop, daemon=True).start()
    # start match daemon co-located so issued assignments are consumable in-process
    try:
        t = threading.Thread(target=_run_match_daemon, daemon=True)
        t.start()
    except Exception:
        traceback.print_exc()

    server = ControlPlaneHTTPServer((HOST, PORT), Handler)
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    print(f"Control-plane listening on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        stop_event.set()
        try:
            server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    run_server()
