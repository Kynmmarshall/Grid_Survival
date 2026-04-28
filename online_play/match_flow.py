"""Match-flow message schema helpers for online play."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


MSG_DISCONNECT = "disconnect"
MSG_GAME_START = "game_start"
MSG_INPUT_STATE = "input_state"
MSG_MATCH_RESULT = "match_result"
MSG_PAUSE_STATE = "pause_state"
MSG_PAUSE_TOGGLE_REQUEST = "pause_toggle_request"
MSG_PLAYER_SETUP = "player_setup"
MSG_RESTART_REQUEST = "restart_request"
MSG_SNAPSHOT = "snapshot"
MSG_WORLD_SNAPSHOT = "world_snapshot"

CRITICAL_MESSAGE_TYPES = frozenset(
    {
        MSG_DISCONNECT,
        MSG_GAME_START,
        MSG_MATCH_RESULT,
        MSG_PAUSE_STATE,
        MSG_PAUSE_TOGGLE_REQUEST,
        MSG_RESTART_REQUEST,
        MSG_PLAYER_SETUP,
    }
)

LATEST_ONLY_MESSAGE_TYPES = frozenset(
    {
        MSG_INPUT_STATE,
        MSG_SNAPSHOT,
        MSG_WORLD_SNAPSHOT,
    }
)

UNRELIABLE_MESSAGE_TYPES = frozenset(
    {
        MSG_INPUT_STATE,
        MSG_SNAPSHOT,
        MSG_WORLD_SNAPSHOT,
    }
)


@dataclass(slots=True)
class NetworkPlayerSetup:
    name: str
    character: str

    def to_message(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MatchSettings:
    level_id: int
    target_score: int

    def to_message(self) -> dict[str, Any]:
        return {
            "level_id": int(self.level_id),
            "target_score": int(self.target_score),
        }


@dataclass(slots=True)
class MatchStartPayload:
    players: list[NetworkPlayerSetup]
    local_player_index: int
    settings: MatchSettings

    def to_message(self) -> dict[str, Any]:
        return {
            "players": [player.to_message() for player in self.players],
            "local_player_index": int(self.local_player_index),
            **self.settings.to_message(),
        }


def build_player_setup_payload(player: NetworkPlayerSetup) -> dict[str, Any]:
    return player.to_message()


def parse_player_setup_message(
    message: Any,
    *,
    default_name: str = "Player 2",
    default_character: str = "Caveman",
) -> NetworkPlayerSetup | None:
    if not isinstance(message, dict):
        return None
    return NetworkPlayerSetup(
        name=str(message.get("name", default_name)),
        character=str(message.get("character", default_character)),
    )


def build_game_start_payload(payload: MatchStartPayload) -> dict[str, Any]:
    return payload.to_message()


def parse_game_start_message(message: Any) -> MatchStartPayload | None:
    if not isinstance(message, dict):
        return None
    raw_players = message.get("players")
    if not isinstance(raw_players, list) or len(raw_players) < 2:
        return None

    players: list[NetworkPlayerSetup] = []
    for idx, entry in enumerate(raw_players[:2]):
        if not isinstance(entry, dict):
            return None
        players.append(
            NetworkPlayerSetup(
                name=str(entry.get("name", f"Player {idx + 1}")),
                character=str(entry.get("character", "Caveman")),
            )
        )

    try:
        local_player_index = int(message.get("local_player_index", 1))
        level_id = int(message.get("level_id", 1))
        target_score = int(message.get("target_score", 3))
    except (TypeError, ValueError):
        return None

    return MatchStartPayload(
        players=players,
        local_player_index=local_player_index,
        settings=MatchSettings(
            level_id=level_id,
            target_score=target_score,
        ),
    )
