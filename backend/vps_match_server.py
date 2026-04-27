from __future__ import annotations

import os
import random
import string
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class MatchAssignment:
    match_id: str
    endpoint: str
    token: str
    created_at: float
    payload: dict[str, Any]


class MatchServerManager:
    """Assignment manager for authoritative match server endpoints.

    This manager issues signed-like opaque tokens and keeps a short-lived
    in-memory registry for reconnect/resync handoff data.
    """

    def __init__(self, endpoint: str, assignment_ttl_seconds: float = 1800.0):
        self.endpoint = str(endpoint).strip() or "udp://127.0.0.1:5555"
        self.assignment_ttl_seconds = max(60.0, float(assignment_ttl_seconds))
        self._lock = threading.Lock()
        self._assignments: dict[str, MatchAssignment] = {}

    @classmethod
    def from_env(cls) -> "MatchServerManager":
        endpoint = os.getenv("GRID_SURVIVAL_MATCH_ENDPOINT", "udp://127.0.0.1:5555")
        ttl = os.getenv("GRID_SURVIVAL_MATCH_ASSIGNMENT_TTL", "1800")
        try:
            ttl_s = float(ttl)
        except (TypeError, ValueError):
            ttl_s = 1800.0
        return cls(endpoint=endpoint, assignment_ttl_seconds=ttl_s)

    @staticmethod
    def _new_token(length: int = 24) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(random.choice(alphabet) for _ in range(max(12, length)))

    def issue_assignment(self, *, match_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        token = self._new_token(24)
        now = time.time()
        assignment = MatchAssignment(
            match_id=str(match_id),
            endpoint=self.endpoint,
            token=token,
            created_at=now,
            payload=dict(payload),
        )

        with self._lock:
            self._purge_locked(now)
            self._assignments[token] = assignment

        return {
            "endpoint": assignment.endpoint,
            "token": assignment.token,
            "expires_in": int(self.assignment_ttl_seconds),
        }

    def consume_assignment(self, token: str) -> dict[str, Any] | None:
        now = time.time()
        with self._lock:
            self._purge_locked(now)
            assignment = self._assignments.get(str(token))
            if assignment is None:
                return None
            return {
                "match_id": assignment.match_id,
                "endpoint": assignment.endpoint,
                "token": assignment.token,
                "payload": dict(assignment.payload),
                "created_at": float(assignment.created_at),
            }

    def _purge_locked(self, now: float) -> None:
        stale = [
            token
            for token, assignment in self._assignments.items()
            if now - float(assignment.created_at) > self.assignment_ttl_seconds
        ]
        for token in stale:
            self._assignments.pop(token, None)
