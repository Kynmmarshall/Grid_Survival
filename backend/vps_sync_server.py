from __future__ import annotations

import json
import os
import sqlite3
import signal
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


def _first_env(*names: str, default: str) -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None:
            clean = str(value).strip()
            if clean:
                return clean
    return default


def _parse_port(value: str, default: int = 8000) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return default
    if 1 <= port <= 65535:
        return port
    return default


DB_PATH = Path(_first_env("GRID_SURVIVAL_VPS_DB", "DB_NAME", default="vps_accounts.db"))
HOST = _first_env("GRID_SURVIVAL_VPS_HOST", "DB_HOST", default="0.0.0.0")
PORT = _parse_port(_first_env("GRID_SURVIVAL_VPS_PORT", "DB_PORT", default="8000"), default=8000)


class SyncApiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class RemoteAccountStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    rr INTEGER NOT NULL DEFAULT 1000,
                    ranked_rating INTEGER NOT NULL DEFAULT 1000,
                    damage_dealt INTEGER NOT NULL DEFAULT 0,
                    damage_taken INTEGER NOT NULL DEFAULT 0,
                    eliminations INTEGER NOT NULL DEFAULT 0,
                    deaths INTEGER NOT NULL DEFAULT 0,
                    rounds_played INTEGER NOT NULL DEFAULT 0,
                    rounds_won INTEGER NOT NULL DEFAULT 0,
                    matches_played INTEGER NOT NULL DEFAULT 0,
                    matches_won INTEGER NOT NULL DEFAULT 0,
                    mvp_count INTEGER NOT NULL DEFAULT 0,
                    unranked_matches_played INTEGER NOT NULL DEFAULT 0,
                    unranked_matches_won INTEGER NOT NULL DEFAULT 0,
                    unranked_rounds_played INTEGER NOT NULL DEFAULT 0,
                    unranked_rounds_won INTEGER NOT NULL DEFAULT 0,
                    unranked_eliminations INTEGER NOT NULL DEFAULT 0,
                    unranked_deaths INTEGER NOT NULL DEFAULT 0,
                    unranked_damage_dealt INTEGER NOT NULL DEFAULT 0,
                    unranked_damage_taken INTEGER NOT NULL DEFAULT 0,
                    unranked_mvp_count INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            self._ensure_account_columns(conn)

    def _ensure_account_columns(self, conn: sqlite3.Connection) -> None:
        existing_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(accounts)").fetchall()
        }
        required_columns = {
            "unranked_matches_played": "INTEGER NOT NULL DEFAULT 0",
            "unranked_matches_won": "INTEGER NOT NULL DEFAULT 0",
            "unranked_rounds_played": "INTEGER NOT NULL DEFAULT 0",
            "unranked_rounds_won": "INTEGER NOT NULL DEFAULT 0",
            "unranked_eliminations": "INTEGER NOT NULL DEFAULT 0",
            "unranked_deaths": "INTEGER NOT NULL DEFAULT 0",
            "unranked_damage_dealt": "INTEGER NOT NULL DEFAULT 0",
            "unranked_damage_taken": "INTEGER NOT NULL DEFAULT 0",
            "unranked_mvp_count": "INTEGER NOT NULL DEFAULT 0",
        }
        for column_name, column_ddl in required_columns.items():
            if column_name in existing_columns:
                continue
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {column_name} {column_ddl}")

    def _normalize_username(self, username: Any) -> str | None:
        if not isinstance(username, str):
            return None
        clean = username.strip()
        if not (3 <= len(clean) <= 24):
            return None
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
        if any(ch not in allowed for ch in clean):
            return None
        return clean

    def get_profile(self, username: str) -> dict[str, Any] | None:
        clean = self._normalize_username(username)
        if clean is None:
            return None

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username, rr, ranked_rating, damage_dealt, damage_taken,
                       eliminations, deaths, rounds_played, rounds_won,
                       matches_played, matches_won, mvp_count,
                       unranked_matches_played, unranked_matches_won,
                       unranked_rounds_played, unranked_rounds_won,
                       unranked_eliminations, unranked_deaths,
                       unranked_damage_dealt, unranked_damage_taken, unranked_mvp_count,
                       created_at, updated_at
                FROM accounts
                WHERE username = ?
                """,
                (clean,),
            ).fetchone()

        if row is None:
            return None

        return {
            "username": str(row["username"]),
            "rr": int(row["rr"]),
            "ranked_rating": int(row["ranked_rating"]),
            "damage_dealt": int(row["damage_dealt"]),
            "damage_taken": int(row["damage_taken"]),
            "eliminations": int(row["eliminations"]),
            "deaths": int(row["deaths"]),
            "rounds_played": int(row["rounds_played"]),
            "rounds_won": int(row["rounds_won"]),
            "matches_played": int(row["matches_played"]),
            "matches_won": int(row["matches_won"]),
            "mvp_count": int(row["mvp_count"]),
            "unranked_matches_played": int(row["unranked_matches_played"]),
            "unranked_matches_won": int(row["unranked_matches_won"]),
            "unranked_rounds_played": int(row["unranked_rounds_played"]),
            "unranked_rounds_won": int(row["unranked_rounds_won"]),
            "unranked_eliminations": int(row["unranked_eliminations"]),
            "unranked_deaths": int(row["unranked_deaths"]),
            "unranked_damage_dealt": int(row["unranked_damage_dealt"]),
            "unranked_damage_taken": int(row["unranked_damage_taken"]),
            "unranked_mvp_count": int(row["unranked_mvp_count"]),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
        }

    def get_leaderboard(self, limit: int, mode: str = "ranked") -> list[dict[str, Any]]:
        capped = max(1, min(200, int(limit)))
        mode_key = "unranked" if str(mode).strip().lower() == "unranked" else "ranked"
        with self._connect() as conn:
            if mode_key == "ranked":
                rows = conn.execute(
                    """
                    SELECT username, rr, matches_played, matches_won, rounds_played, rounds_won,
                           eliminations, deaths, damage_dealt, damage_taken, mvp_count
                    FROM accounts
                    ORDER BY rr DESC, rounds_won DESC, mvp_count DESC, updated_at ASC
                    LIMIT ?
                    """,
                    (capped,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT username,
                           unranked_matches_played AS matches_played,
                           unranked_matches_won AS matches_won,
                           unranked_rounds_played AS rounds_played,
                           unranked_rounds_won AS rounds_won,
                           unranked_eliminations AS eliminations,
                           unranked_deaths AS deaths,
                           unranked_damage_dealt AS damage_dealt,
                           unranked_damage_taken AS damage_taken,
                           unranked_mvp_count AS mvp_count
                    FROM accounts
                    ORDER BY unranked_matches_won DESC,
                             unranked_rounds_won DESC,
                             unranked_mvp_count DESC,
                             updated_at ASC
                    LIMIT ?
                    """,
                    (capped,),
                ).fetchall()

        leaderboard: list[dict[str, Any]] = []
        for pos, row in enumerate(rows, start=1):
            matches_won = int(row["matches_won"])
            rounds_won = int(row["rounds_won"])
            eliminations = int(row["eliminations"])
            deaths = int(row["deaths"])
            mvp_count = int(row["mvp_count"])
            if mode_key == "ranked":
                rating_value = int(row["rr"])
            else:
                rating_value = max(0, matches_won * 20 + rounds_won * 6 + eliminations * 2 + mvp_count * 10 - deaths)

            leaderboard.append(
                {
                    "position": pos,
                    "username": str(row["username"]),
                    "mode": mode_key,
                    "rating": int(rating_value),
                    "rr": int(rating_value),
                    "matches_played": int(row["matches_played"]),
                    "matches_won": matches_won,
                    "rounds_played": int(row["rounds_played"]),
                    "rounds_won": rounds_won,
                    "eliminations": eliminations,
                    "deaths": deaths,
                    "damage_dealt": int(row["damage_dealt"]),
                    "damage_taken": int(row["damage_taken"]),
                    "mvp_count": mvp_count,
                }
            )
        return leaderboard

    def apply_sync_event(self, event: dict[str, Any]) -> dict[str, Any]:
        username = self._normalize_username(event.get("username"))
        event_type = str(event.get("event_type", "")).strip()
        payload = event.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        if username is None:
            return {"ok": False, "error": "invalid username"}
        if not event_type:
            return {"ok": False, "error": "missing event_type"}

        now = float(payload.get("updated_at", time.time()))

        if event_type == "account_created":
            self._upsert_account_created(username, payload, now)
        elif event_type == "stat_delta":
            self._apply_stat_delta(username, payload, now)
        else:
            return {"ok": False, "error": f"unsupported event_type: {event_type}"}

        profile = self.get_profile(username)
        return {"ok": True, "profile": profile}

    def _upsert_account_created(self, username: str, payload: dict[str, Any], now: float) -> None:
        rr = int(payload.get("rr", 1000))
        rr = max(0, rr)
        created_at = float(payload.get("created_at", now))

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT username FROM accounts WHERE username = ?",
                (username,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO accounts (
                        username, rr, ranked_rating,
                        damage_dealt, damage_taken, eliminations, deaths,
                        rounds_played, rounds_won, matches_played, matches_won,
                        mvp_count, created_at, updated_at
                    ) VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, ?)
                    """,
                    (username, rr, rr, created_at, now),
                )
            else:
                conn.execute(
                    """
                    UPDATE accounts
                    SET rr = ?, ranked_rating = ?, updated_at = ?
                    WHERE username = ?
                    """,
                    (rr, rr, now, username),
                )

    def _apply_stat_delta(self, username: str, payload: dict[str, Any], now: float) -> None:
        with self._connect() as conn:
            ranked_mode = bool(payload.get("ranked", True))
            existing = conn.execute(
                "SELECT username, rr FROM accounts WHERE username = ?",
                (username,),
            ).fetchone()
            if existing is None:
                base_rr = max(0, int(payload.get("rr_after", 1000)))
                conn.execute(
                    """
                    INSERT INTO accounts (
                        username, rr, ranked_rating,
                        damage_dealt, damage_taken, eliminations, deaths,
                        rounds_played, rounds_won, matches_played, matches_won,
                        mvp_count, created_at, updated_at
                    ) VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, ?)
                    """,
                    (username, base_rr, base_rr, now, now),
                )
                existing_rr = base_rr
            else:
                existing_rr = int(existing["rr"])

            if ranked_mode:
                if "rr_after" in payload:
                    next_rr = max(0, int(payload.get("rr_after", existing_rr)))
                else:
                    next_rr = max(0, existing_rr + int(payload.get("rr_delta", 0)))

                conn.execute(
                    """
                    UPDATE accounts
                    SET rr = ?,
                        ranked_rating = ?,
                        damage_dealt = damage_dealt + ?,
                        damage_taken = damage_taken + ?,
                        eliminations = eliminations + ?,
                        deaths = deaths + ?,
                        rounds_played = rounds_played + ?,
                        rounds_won = rounds_won + ?,
                        matches_played = matches_played + ?,
                        matches_won = matches_won + ?,
                        mvp_count = mvp_count + ?,
                        updated_at = ?
                    WHERE username = ?
                    """,
                    (
                        next_rr,
                        next_rr,
                        int(max(0, payload.get("damage_dealt", 0))),
                        int(max(0, payload.get("damage_taken", 0))),
                        int(max(0, payload.get("eliminations", 0))),
                        int(max(0, payload.get("deaths", 0))),
                        int(max(0, payload.get("rounds_played", 0))),
                        int(max(0, payload.get("rounds_won", 0))),
                        int(max(0, payload.get("matches_played", 0))),
                        int(max(0, payload.get("matches_won", 0))),
                        int(max(0, payload.get("mvp_count", 0))),
                        now,
                        username,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE accounts
                    SET unranked_damage_dealt = unranked_damage_dealt + ?,
                        unranked_damage_taken = unranked_damage_taken + ?,
                        unranked_eliminations = unranked_eliminations + ?,
                        unranked_deaths = unranked_deaths + ?,
                        unranked_rounds_played = unranked_rounds_played + ?,
                        unranked_rounds_won = unranked_rounds_won + ?,
                        unranked_matches_played = unranked_matches_played + ?,
                        unranked_matches_won = unranked_matches_won + ?,
                        unranked_mvp_count = unranked_mvp_count + ?,
                        updated_at = ?
                    WHERE username = ?
                    """,
                    (
                        int(max(0, payload.get("damage_dealt", 0))),
                        int(max(0, payload.get("damage_taken", 0))),
                        int(max(0, payload.get("eliminations", 0))),
                        int(max(0, payload.get("deaths", 0))),
                        int(max(0, payload.get("rounds_played", 0))),
                        int(max(0, payload.get("rounds_won", 0))),
                        int(max(0, payload.get("matches_played", 0))),
                        int(max(0, payload.get("matches_won", 0))),
                        int(max(0, payload.get("mvp_count", 0))),
                        now,
                        username,
                    ),
                )


class SyncApiHandler(BaseHTTPRequestHandler):
    store = RemoteAccountStore(DB_PATH)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "" or path == "/health":
            self._send_json(HTTPStatus.OK, {"ok": True, "server_time": time.time()})
            return

        if path == "/leaderboard":
            qs = urllib.parse.parse_qs(parsed.query)
            limit = int(qs.get("limit", ["50"])[0])
            mode = str(qs.get("mode", ["ranked"])[0])
            board = self.store.get_leaderboard(limit, mode=mode)
            self._send_json(HTTPStatus.OK, {"leaderboard": board, "mode": mode})
            return

        if path.startswith("/profiles/"):
            username = urllib.parse.unquote(path.split("/profiles/", 1)[1]).strip()
            profile = self.store.get_profile(username)
            if profile is None:
                self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "profile not found"})
                return
            self._send_json(HTTPStatus.OK, profile)
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path not in {"/sync/events", "/events"}:
            self._send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return

        payload = self._read_json_body()
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid json body"})
            return

        result = self.store.apply_sync_event(payload)
        if result.get("ok"):
            self._send_json(HTTPStatus.OK, result)
        else:
            self._send_json(HTTPStatus.BAD_REQUEST, result)

    def _read_json_body(self) -> Any | None:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0:
            return None

        body = self.rfile.read(content_length)
        try:
            return json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[sync-api] {self.address_string()} - {fmt % args}")


def main() -> None:
    server = SyncApiServer((HOST, PORT), SyncApiHandler)
    stop_requested = threading.Event()

    def _request_stop(*_args: object) -> None:
        stop_requested.set()
        try:
            server.shutdown()
        except Exception:
            pass

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    print(f"Grid Survival sync API listening on http://{HOST}:{PORT}")
    print(f"Using DB: {DB_PATH.resolve()}")
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        stop_requested.set()
        server.server_close()


if __name__ == "__main__":
    main()
