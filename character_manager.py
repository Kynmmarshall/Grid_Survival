"""Utility helpers for character discovery and animation path lookups."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

from settings import ASSETS_DIR, CHARACTER_BASE, PLAYER_ANIMATION_PATHS

CHARACTERS_DIR = ASSETS_DIR / "Characters"
DEFAULT_CHARACTER_NAME = CHARACTER_BASE.name if CHARACTER_BASE else "Caveman"

_STATE_STRUCTURE: Dict[str, Dict[str, tuple[str, ...]]] = {
    "idle": {
        "down": ("idle", "Front - Idle Blinking"),
        "up": ("idle", "Back - Idle"),
        "left": ("idle", "Left - Idle Blinking"),
        "right": ("idle", "Right - Idle Blinking"),
    },
    "run": {
        "down": ("running", "Front - Running"),
        "up": ("running", "Back - Running"),
        "left": ("running", "Left - Running"),
        "right": ("running", "Right - Running"),
    },
    "death": {
        "down": ("Dying",),
        "up": ("Dying",),
        "left": ("Dying",),
        "right": ("Dying",),
    },
}


def available_characters() -> list[str]:
    """Return every playable character folder that has idle + running sets."""
    names: list[str] = []
    if CHARACTERS_DIR.exists():
        for entry in CHARACTERS_DIR.iterdir():
            if not entry.is_dir() or entry.name.startswith('.'):
                continue
            if _has_required_dirs(entry):
                names.append(entry.name)
    if DEFAULT_CHARACTER_NAME not in names:
        names.append(DEFAULT_CHARACTER_NAME)
    return sorted(set(names))


def build_animation_paths(character_name: str | None = None) -> Dict[str, Dict[str, Path]]:
    """Resolve animation directories for a character, falling back to default."""
    paths = _clone_default_paths()
    target_name = (character_name or DEFAULT_CHARACTER_NAME).strip() or DEFAULT_CHARACTER_NAME
    candidate = CHARACTERS_DIR / target_name
    if candidate.exists():
        custom = _collect_paths(candidate)
        for state, directions in paths.items():
            for direction in directions:
                source = custom.get(state, {}).get(direction)
                if source is not None and source.exists():
                    paths[state][direction] = source
    return paths


def _collect_paths(base: Path) -> Dict[str, Dict[str, Path]]:
    resolved: Dict[str, Dict[str, Path]] = {}
    for state, direction_map in _STATE_STRUCTURE.items():
        resolved[state] = {}
        for direction, rel_parts in direction_map.items():
            path = _resolve_relative(base, rel_parts)
            if path is not None:
                resolved[state][direction] = path
    return resolved


def _resolve_relative(base: Path, rel_parts: tuple[str, ...]) -> Path | None:
    current = base
    for part in rel_parts:
        match = _case_insensitive_child(current, part)
        if match is None:
            return None
        current = match
    return current


def _case_insensitive_child(parent: Path, target: str) -> Path | None:
    if not parent.exists():
        return None
    target_lower = target.lower()
    for child in parent.iterdir():
        if child.is_dir() and child.name.lower() == target_lower:
            return child
    return None


def _has_required_dirs(path: Path) -> bool:
    try:
        subdirs = {child.name.lower() for child in path.iterdir() if child.is_dir()}
    except FileNotFoundError:
        return False
    return "idle" in subdirs and "running" in subdirs


def _clone_default_paths() -> Dict[str, Dict[str, Path]]:
    clones: Dict[str, Dict[str, Path]] = {}
    for state, directions in PLAYER_ANIMATION_PATHS.items():
        clones[state] = {direction: path for direction, path in directions.items()}
    return clones
