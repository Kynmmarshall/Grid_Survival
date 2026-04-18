from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


DEFAULT_RR = 10
DEFAULT_API_TIMEOUT = 4.0


@dataclass
class AccountProfile:
    username: str
    rr: int
    ranked_rating: int
    matches_played: int
    matches_won: int
    rounds_played: int
    rounds_won: int
    eliminations: int
    deaths: int
    damage_dealt: int
    damage_taken: int
    mvp_count: int
    unranked_matches_played: int
    unranked_matches_won: int
    unranked_rounds_played: int
    unranked_rounds_won: int
    unranked_eliminations: int
    unranked_deaths: int
    unranked_damage_dealt: int
    unranked_damage_taken: int
    unranked_mvp_count: int
    created_at: float
    updated_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "rr": int(self.rr),
            "ranked_rating": int(self.ranked_rating),
            "matches_played": int(self.matches_played),
            "matches_won": int(self.matches_won),
            "rounds_played": int(self.rounds_played),
            "rounds_won": int(self.rounds_won),
            "eliminations": int(self.eliminations),
            "deaths": int(self.deaths),
            "damage_dealt": int(self.damage_dealt),
            "damage_taken": int(self.damage_taken),
            "mvp_count": int(self.mvp_count),
            "unranked_matches_played": int(self.unranked_matches_played),
            "unranked_matches_won": int(self.unranked_matches_won),
            "unranked_rounds_played": int(self.unranked_rounds_played),
            "unranked_rounds_won": int(self.unranked_rounds_won),
            "unranked_eliminations": int(self.unranked_eliminations),
            "unranked_deaths": int(self.unranked_deaths),
            "unranked_damage_dealt": int(self.unranked_damage_dealt),
            "unranked_damage_taken": int(self.unranked_damage_taken),
            "unranked_mvp_count": int(self.unranked_mvp_count),
            "created_at": float(self.created_at),
            "updated_at": float(self.updated_at),
        }


class AccountService:
    """Local-first account storage with optional external sync.

    The service always writes to local SQLite first, then enqueues sync events.
    When online and API is configured, queued events are pushed to the VPS API.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        api_base_url: str | None = None,
        api_timeout: float = DEFAULT_API_TIMEOUT,
    ):
        self.db_path = db_path or self._resolve_db_path()
        self.api_base_url = (api_base_url or os.getenv("GRID_SURVIVAL_API_URL", "http://38.242.246.126:8001")).strip()
        self.api_timeout = float(max(1.0, api_timeout))
        self._ensure_schema()

    def register_account(self, username: str, password: str) -> tuple[bool, str]:
        clean_username = self._validate_username(username)
        if clean_username is None:
            return False, "Username must be 3-24 chars (letters, numbers, underscore)."
        if len(password) < 4:
            return False, "Password must be at least 4 characters."

        existing = self.get_profile(clean_username)
        if existing is not None:
            return False, "Username already exists."

        salt = secrets.token_hex(16)
        password_hash = self._hash_password(password, salt)
        now = time.time()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts (
                    username, password_hash, password_salt, rr, ranked_rating,
                    damage_dealt, damage_taken, eliminations, deaths,
                    rounds_played, rounds_won, matches_played, matches_won,
                    mvp_count, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, ?)
                """,
                (
                    clean_username,
                    password_hash,
                    salt,
                    DEFAULT_RR,
                    DEFAULT_RR,
                    now,
                    now,
                ),
            )

        self._queue_sync_event(
            clean_username,
            "account_created",
            {
                "username": clean_username,
                "rr": DEFAULT_RR,
                "created_at": now,
            },
        )
        self.sync_pending(clean_username)
        return True, "Account created."

    def authenticate(self, username: str, password: str) -> tuple[bool, str]:
        clean_username = self._validate_username(username)
        if clean_username is None:
            return False, "Invalid username format."

        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash, password_salt FROM accounts WHERE username = ?",
                (clean_username,),
            ).fetchone()

        if row is None:
            if not self.is_remote_online():
                return (
                    False,
                    "Account not found locally. Connect to internet and try login again to check your online account.",
                )

            remote_status, remote_profile = self._fetch_remote_profile_status(clean_username)
            if remote_status == "found" and isinstance(remote_profile, dict):
                created = self._create_local_account_from_remote(
                    clean_username,
                    password,
                    remote_profile,
                )
                if created:
                    self.sync_pending(clean_username)
                    return True, "Online account found. Local profile restored and login successful."

                # If another process created it at the same time, retry local auth once.
                with self._connect() as conn:
                    row = conn.execute(
                        "SELECT password_hash, password_salt FROM accounts WHERE username = ?",
                        (clean_username,),
                    ).fetchone()
                if row is None:
                    return False, "Could not restore local profile. Please try again."
            elif remote_status == "missing":
                return False, "Account not found on local or online server. Please register a new account."
            else:
                return (
                    False,
                    "Account not found locally, and online check failed. Connect to internet and try again.",
                )

        check_hash = self._hash_password(password, row["password_salt"])
        if not secrets.compare_digest(check_hash, row["password_hash"]):
            return False, "Incorrect password."

        self.sync_pending(clean_username)
        return True, "Login successful."

    def get_profile(self, username: str) -> AccountProfile | None:
        clean_username = self._validate_username(username)
        if clean_username is None:
            return None

        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username, rr, ranked_rating, matches_played, matches_won,
                       rounds_played, rounds_won, eliminations, deaths,
                       damage_dealt, damage_taken, mvp_count,
                       unranked_matches_played, unranked_matches_won,
                       unranked_rounds_played, unranked_rounds_won,
                       unranked_eliminations, unranked_deaths,
                       unranked_damage_dealt, unranked_damage_taken, unranked_mvp_count,
                       created_at, updated_at
                FROM accounts
                WHERE username = ?
                """,
                (clean_username,),
            ).fetchone()

        if row is None:
            return None
        return self._row_to_profile(row)

    def get_recent_account_username(self) -> str | None:
        """Return the most recently updated local account username, if any."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT username
                FROM accounts
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None
        username = self._validate_username(str(row["username"]))
        return username

    def apply_stat_delta(
        self,
        username: str,
        *,
        rr_delta: int = 0,
        damage_dealt: int = 0,
        damage_taken: int = 0,
        eliminations: int = 0,
        deaths: int = 0,
        rounds_played: int = 0,
        rounds_won: int = 0,
        matches_played: int = 0,
        matches_won: int = 0,
        mvp_count: int = 0,
        ranked: bool = True,
        sync_now: bool = True,
    ) -> AccountProfile | None:
        profile = self.get_profile(username)
        if profile is None:
            return None

        ranked_mode = bool(ranked)
        now = time.time()
        next_rr = int(profile.rr)
        if ranked_mode:
            next_rr = max(0, int(profile.rr) + int(rr_delta))

        with self._connect() as conn:
            if ranked_mode:
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
                        int(max(0, damage_dealt)),
                        int(max(0, damage_taken)),
                        int(max(0, eliminations)),
                        int(max(0, deaths)),
                        int(max(0, rounds_played)),
                        int(max(0, rounds_won)),
                        int(max(0, matches_played)),
                        int(max(0, matches_won)),
                        int(max(0, mvp_count)),
                        now,
                        profile.username,
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
                        int(max(0, damage_dealt)),
                        int(max(0, damage_taken)),
                        int(max(0, eliminations)),
                        int(max(0, deaths)),
                        int(max(0, rounds_played)),
                        int(max(0, rounds_won)),
                        int(max(0, matches_played)),
                        int(max(0, matches_won)),
                        int(max(0, mvp_count)),
                        now,
                        profile.username,
                    ),
                )

        sync_payload = {
            "username": profile.username,
            "ranked": bool(ranked_mode),
            "rr_delta": int(rr_delta) if ranked_mode else 0,
            "rr_after": int(next_rr),
            "damage_dealt": int(max(0, damage_dealt)),
            "damage_taken": int(max(0, damage_taken)),
            "eliminations": int(max(0, eliminations)),
            "deaths": int(max(0, deaths)),
            "rounds_played": int(max(0, rounds_played)),
            "rounds_won": int(max(0, rounds_won)),
            "matches_played": int(max(0, matches_played)),
            "matches_won": int(max(0, matches_won)),
            "mvp_count": int(max(0, mvp_count)),
            "updated_at": now,
        }
        self._queue_sync_event(profile.username, "stat_delta", sync_payload)
        if sync_now:
            self.sync_pending(profile.username)
        return self.get_profile(profile.username)

    def get_local_leaderboard(self, limit: int = 50, mode: str = "ranked") -> list[dict[str, Any]]:
        capped_limit = max(1, min(200, int(limit)))
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
                    (capped_limit,),
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
                    (capped_limit,),
                ).fetchall()

        board: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            matches_won = int(row["matches_won"])
            matches_played = int(row["matches_played"])
            rounds_won = int(row["rounds_won"])
            rounds_played = int(row["rounds_played"])
            eliminations = int(row["eliminations"])
            deaths = int(row["deaths"])
            damage_dealt = int(row["damage_dealt"])
            damage_taken = int(row["damage_taken"])
            mvp_count = int(row["mvp_count"])
            if mode_key == "ranked":
                rating_value = int(row["rr"])
            else:
                rating_value = max(0, matches_won * 20 + rounds_won * 6 + eliminations * 2 + mvp_count * 10 - deaths)

            board.append(
                {
                    "position": index,
                    "username": str(row["username"]),
                    "mode": mode_key,
                    "rating": int(rating_value),
                    "rr": int(rating_value),
                    "matches_played": matches_played,
                    "matches_won": matches_won,
                    "rounds_played": rounds_played,
                    "rounds_won": rounds_won,
                    "eliminations": eliminations,
                    "deaths": deaths,
                    "damage_dealt": damage_dealt,
                    "damage_taken": damage_taken,
                    "mvp_count": mvp_count,
                }
            )
        return board

    def get_local_position(self, username: str) -> int | None:
        clean_username = self._validate_username(username)
        if clean_username is None:
            return None

        rows = self.get_local_leaderboard(limit=2000)
        for row in rows:
            if row.get("username") == clean_username:
                return int(row.get("position", 0))
        return None

    def fetch_remote_leaderboard(self, limit: int = 50, mode: str = "ranked") -> list[dict[str, Any]] | None:
        if not self._has_remote():
            return None

        capped_limit = max(1, min(200, int(limit)))
        mode_key = "unranked" if str(mode).strip().lower() == "unranked" else "ranked"
        query = urllib.parse.urlencode({"limit": capped_limit, "mode": mode_key})
        payload = self._request_json("GET", f"/leaderboard?{query}")
        if payload is None:
            return None

        if isinstance(payload, dict):
            candidates = payload.get("leaderboard")
        else:
            candidates = payload

        if not isinstance(candidates, list):
            return None

        leaderboard: list[dict[str, Any]] = []
        for index, item in enumerate(candidates, start=1):
            if not isinstance(item, dict):
                continue
            username = str(item.get("username", ""))
            if not username:
                continue

            matches_played = int(item.get("matches_played", item.get("unranked_matches_played", 0)))
            matches_won = int(item.get("matches_won", item.get("unranked_matches_won", 0)))
            rounds_played = int(item.get("rounds_played", item.get("unranked_rounds_played", 0)))
            rounds_won = int(item.get("rounds_won", item.get("unranked_rounds_won", 0)))
            eliminations = int(item.get("eliminations", item.get("unranked_eliminations", 0)))
            deaths = int(item.get("deaths", item.get("unranked_deaths", 0)))
            damage_dealt = int(item.get("damage_dealt", item.get("unranked_damage_dealt", 0)))
            damage_taken = int(item.get("damage_taken", item.get("unranked_damage_taken", 0)))
            mvp_count = int(item.get("mvp_count", item.get("unranked_mvp_count", 0)))
            if mode_key == "ranked":
                rating_value = int(item.get("rating", item.get("rr", item.get("ranked_rating", 0))))
            else:
                rating_value = int(
                    item.get(
                        "rating",
                        max(0, matches_won * 20 + rounds_won * 6 + eliminations * 2 + mvp_count * 10 - deaths),
                    )
                )

            leaderboard.append(
                {
                    "position": int(item.get("position", index)),
                    "username": username,
                    "mode": mode_key,
                    "rating": int(rating_value),
                    "rr": int(rating_value),
                    "matches_played": matches_played,
                    "matches_won": matches_won,
                    "rounds_played": rounds_played,
                    "rounds_won": rounds_won,
                    "eliminations": eliminations,
                    "deaths": deaths,
                    "damage_dealt": damage_dealt,
                    "damage_taken": damage_taken,
                    "mvp_count": mvp_count,
                }
            )

        return leaderboard

    def sync_pending(self, username: str | None = None) -> bool:
        """Attempt to push queued updates to VPS and pull latest profile data."""
        if not self._has_remote():
            return False

        if not self.is_remote_online():
            return False

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, username, event_type, payload_json, attempts
                FROM sync_queue
                ORDER BY id ASC
                LIMIT 120
                """
            ).fetchall()

        any_success = False
        for row in rows:
            payload_json = str(row["payload_json"])
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                payload = {"raw": payload_json}

            event = {
                "username": str(row["username"]),
                "event_type": str(row["event_type"]),
                "payload": payload,
                "attempts": int(row["attempts"]),
            }

            delivered = self._push_sync_event(event)
            with self._connect() as conn:
                if delivered:
                    conn.execute("DELETE FROM sync_queue WHERE id = ?", (int(row["id"]),))
                    any_success = True
                else:
                    conn.execute(
                        "UPDATE sync_queue SET attempts = attempts + 1 WHERE id = ?",
                        (int(row["id"]),),
                    )

        if username:
            self._pull_remote_profile(username)

        return any_success

    def is_remote_online(self) -> bool:
        if not self._has_remote():
            return False

        payload = self._request_json("GET", "/health")
        if payload is None:
            # Some APIs do not have a health endpoint. Try a lightweight leaderboard call.
            fallback = self._request_json("GET", "/leaderboard?limit=1")
            return fallback is not None
        return True

    def _ensure_schema(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0
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

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _queue_sync_event(self, username: str, event_type: str, payload: dict[str, Any]) -> None:
        now = time.time()
        serialized = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sync_queue (username, event_type, payload_json, created_at, attempts)
                VALUES (?, ?, ?, ?, 0)
                """,
                (username, event_type, serialized, now),
            )

    def _push_sync_event(self, event: dict[str, Any]) -> bool:
        if not self._has_remote():
            return False

        response = self._request_json("POST", "/sync/events", event)
        if response is not None:
            return True

        # Fallback path for APIs using /events instead.
        response = self._request_json("POST", "/events", event)
        return response is not None

    def _fetch_remote_profile_status(self, username: str) -> tuple[str, dict[str, Any] | None]:
        if not self._has_remote():
            return "unreachable", None

        encoded = urllib.parse.quote(username)
        url = self.api_base_url.rstrip("/") + f"/profiles/{encoded}"
        request = urllib.request.Request(url=url, headers={"Accept": "application/json"}, method="GET")

        try:
            with urllib.request.urlopen(request, timeout=self.api_timeout) as response:
                body = response.read().decode("utf-8", errors="replace").strip()
        except urllib.error.HTTPError as exc:
            if int(getattr(exc, "code", 0)) == 404:
                return "missing", None
            return "unreachable", None
        except (urllib.error.URLError, TimeoutError, ValueError):
            return "unreachable", None

        if not body:
            return "unreachable", None

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return "unreachable", None

        if isinstance(payload, dict):
            return "found", payload
        return "unreachable", None

    def _create_local_account_from_remote(
        self,
        username: str,
        password: str,
        remote_profile: dict[str, Any],
    ) -> bool:
        salt = secrets.token_hex(16)
        password_hash = self._hash_password(password, salt)
        now = time.time()
        rr_value = max(0, int(remote_profile.get("rr", remote_profile.get("ranked_rating", DEFAULT_RR))))
        created_at = float(remote_profile.get("created_at", now))
        updated_at = float(remote_profile.get("updated_at", now))

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT username FROM accounts WHERE username = ?",
                (username,),
            ).fetchone()
            if existing is not None:
                return False

            conn.execute(
                """
                INSERT INTO accounts (
                    username, password_hash, password_salt, rr, ranked_rating,
                    damage_dealt, damage_taken, eliminations, deaths,
                    rounds_played, rounds_won, matches_played, matches_won,
                    mvp_count,
                    unranked_matches_played, unranked_matches_won,
                    unranked_rounds_played, unranked_rounds_won,
                    unranked_eliminations, unranked_deaths,
                    unranked_damage_dealt, unranked_damage_taken, unranked_mvp_count,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    password_hash,
                    salt,
                    rr_value,
                    rr_value,
                    int(max(0, remote_profile.get("damage_dealt", 0))),
                    int(max(0, remote_profile.get("damage_taken", 0))),
                    int(max(0, remote_profile.get("eliminations", 0))),
                    int(max(0, remote_profile.get("deaths", 0))),
                    int(max(0, remote_profile.get("rounds_played", 0))),
                    int(max(0, remote_profile.get("rounds_won", 0))),
                    int(max(0, remote_profile.get("matches_played", 0))),
                    int(max(0, remote_profile.get("matches_won", 0))),
                    int(max(0, remote_profile.get("mvp_count", 0))),
                    int(max(0, remote_profile.get("unranked_matches_played", 0))),
                    int(max(0, remote_profile.get("unranked_matches_won", 0))),
                    int(max(0, remote_profile.get("unranked_rounds_played", 0))),
                    int(max(0, remote_profile.get("unranked_rounds_won", 0))),
                    int(max(0, remote_profile.get("unranked_eliminations", 0))),
                    int(max(0, remote_profile.get("unranked_deaths", 0))),
                    int(max(0, remote_profile.get("unranked_damage_dealt", 0))),
                    int(max(0, remote_profile.get("unranked_damage_taken", 0))),
                    int(max(0, remote_profile.get("unranked_mvp_count", 0))),
                    created_at,
                    updated_at,
                ),
            )
        return True

    def _pull_remote_profile(self, username: str) -> None:
        if not self._has_remote():
            return

        encoded = urllib.parse.quote(username)
        payload = self._request_json("GET", f"/profiles/{encoded}")
        if payload is None or not isinstance(payload, dict):
            return

        rr_value = int(payload.get("rr", payload.get("ranked_rating", DEFAULT_RR)))
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT username FROM accounts WHERE username = ?",
                (username,),
            ).fetchone()
            if existing is None:
                return

            conn.execute(
                """
                UPDATE accounts
                SET rr = ?,
                    ranked_rating = ?,
                    damage_dealt = ?,
                    damage_taken = ?,
                    eliminations = ?,
                    deaths = ?,
                    rounds_played = ?,
                    rounds_won = ?,
                    matches_played = ?,
                    matches_won = ?,
                    mvp_count = ?,
                    unranked_matches_played = ?,
                    unranked_matches_won = ?,
                    unranked_rounds_played = ?,
                    unranked_rounds_won = ?,
                    unranked_eliminations = ?,
                    unranked_deaths = ?,
                    unranked_damage_dealt = ?,
                    unranked_damage_taken = ?,
                    unranked_mvp_count = ?,
                    updated_at = ?
                WHERE username = ?
                """,
                (
                    rr_value,
                    rr_value,
                    int(payload.get("damage_dealt", 0)),
                    int(payload.get("damage_taken", 0)),
                    int(payload.get("eliminations", 0)),
                    int(payload.get("deaths", 0)),
                    int(payload.get("rounds_played", 0)),
                    int(payload.get("rounds_won", 0)),
                    int(payload.get("matches_played", 0)),
                    int(payload.get("matches_won", 0)),
                    int(payload.get("mvp_count", 0)),
                    int(payload.get("unranked_matches_played", 0)),
                    int(payload.get("unranked_matches_won", 0)),
                    int(payload.get("unranked_rounds_played", 0)),
                    int(payload.get("unranked_rounds_won", 0)),
                    int(payload.get("unranked_eliminations", 0)),
                    int(payload.get("unranked_deaths", 0)),
                    int(payload.get("unranked_damage_dealt", 0)),
                    int(payload.get("unranked_damage_taken", 0)),
                    int(payload.get("unranked_mvp_count", 0)),
                    float(payload.get("updated_at", time.time())),
                    username,
                ),
            )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any | None:
        if not self._has_remote():
            return None

        url = self.api_base_url.rstrip("/") + path
        data_bytes: bytes | None = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data_bytes = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url=url, data=data_bytes, headers=headers, method=method)

        try:
            with urllib.request.urlopen(request, timeout=self.api_timeout) as response:
                body = response.read().decode("utf-8", errors="replace").strip()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
            return None

        if not body:
            return {}

        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None

    def _has_remote(self) -> bool:
        return bool(self.api_base_url)

    def _hash_password(self, password: str, salt: str) -> str:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            120000,
        )
        return digest.hex()

    def _validate_username(self, value: str) -> str | None:
        if not isinstance(value, str):
            return None
        username = value.strip()
        if not (3 <= len(username) <= 24):
            return None
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
        if any(ch not in allowed for ch in username):
            return None
        return username

    def _resolve_db_path(self) -> Path:
        if getattr(sys, "frozen", False):
            appdata = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
            if appdata:
                return Path(appdata) / "Grid_Survival" / "player_accounts.db"
            return Path.home() / ".grid_survival" / "player_accounts.db"
        # Keep source-run DB in repository root even though service lives in backend/.
        return Path(__file__).resolve().parent.parent / "player_accounts.db"

    def _row_to_profile(self, row: sqlite3.Row) -> AccountProfile:
        return AccountProfile(
            username=str(row["username"]),
            rr=int(row["rr"]),
            ranked_rating=int(row["ranked_rating"]),
            matches_played=int(row["matches_played"]),
            matches_won=int(row["matches_won"]),
            rounds_played=int(row["rounds_played"]),
            rounds_won=int(row["rounds_won"]),
            eliminations=int(row["eliminations"]),
            deaths=int(row["deaths"]),
            damage_dealt=int(row["damage_dealt"]),
            damage_taken=int(row["damage_taken"]),
            mvp_count=int(row["mvp_count"]),
            unranked_matches_played=int(row["unranked_matches_played"]),
            unranked_matches_won=int(row["unranked_matches_won"]),
            unranked_rounds_played=int(row["unranked_rounds_played"]),
            unranked_rounds_won=int(row["unranked_rounds_won"]),
            unranked_eliminations=int(row["unranked_eliminations"]),
            unranked_deaths=int(row["unranked_deaths"]),
            unranked_damage_dealt=int(row["unranked_damage_dealt"]),
            unranked_damage_taken=int(row["unranked_damage_taken"]),
            unranked_mvp_count=int(row["unranked_mvp_count"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )
