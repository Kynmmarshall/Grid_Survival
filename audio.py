"""Centralized audio management for Grid Survival."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Union

import pygame

from settings import ASSETS_DIR

DEFAULT_MUSIC_PATH = ASSETS_DIR / "Audio" / "Background" / "Grid survival 1.mp3"
SFX_DIR = ASSETS_DIR / "sounds"


class AudioManager:
    """Centralized wrapper around pygame.mixer for music and SFX."""

    def __init__(self):
        self._initialized = False
        self._current_music: Optional[Path] = None
        self._sfx_cache: Dict[Path, pygame.mixer.Sound] = {}
        self._is_muted = False
        self._music_volume = 0.45  # Default volume
        self._ensure_mixer()

    def _ensure_mixer(self):
        if self._initialized:
            return
        try:
            pygame.mixer.init()
            self._initialized = True
        except pygame.error as exc:
            print(f"[Audio] Unable to initialize mixer: {exc}")

    def play_music(
        self,
        track: Union[str, Path, None] = None,
        *,
        loop: bool = True,
        fade_ms: int = 1500,
        volume: Optional[float] = None,
        restart: bool = True,
    ):
        self._ensure_mixer()
        if not self._initialized:
            return

        music_path = self._resolve_music_path(track)
        if music_path is None:
            print(f"[Audio] Music file not found: {track}")
            return

        try:
            if restart or self._current_music != music_path:
                pygame.mixer.music.load(music_path.as_posix())
                self._current_music = music_path
            
            if volume is not None:
                self._music_volume = self._clamp_volume(volume)
            
            # Apply volume based on mute state
            effective_vol = 0.0 if self._is_muted else self._music_volume
            pygame.mixer.music.set_volume(effective_vol)

            loops = -1 if loop else 0
            pygame.mixer.music.play(loops=loops, fade_ms=max(0, fade_ms))
        except pygame.error as exc:
            print(f"[Audio] Failed to play music '{music_path}': {exc}")

    def stop_music(self, fade_ms: int = 1000):
        self._ensure_mixer()
        if not self._initialized or not pygame.mixer.music.get_busy():
            return
        if fade_ms > 0:
            pygame.mixer.music.fadeout(fade_ms)
        else:
            pygame.mixer.music.stop()

    def play_sfx(
        self,
        identifier: Union[str, P or self._is_mutedath],
        *,
        volume: float = 1.0,
        cache: bool = True,
    ):
        self._ensure_mixer()
        if not self._initialized:
            return

        sound_path = self._resolve_sfx_path(identifier)
        if sound_path is None:
            print(f"[Audio] SFX not found: {identifier}")
            return

        try:
            sound = self._sfx_cache.get(sound_path)
            if sound is None:
                sound = pygame.mixer.Sound(sound_path.as_posix())
                if cache:
                    self._sfx_cache[sound_path] = sound
            channel = sound.play()
            if channel is not None:
                channel.set_volume(self._clamp_volume(volume))
        except pygame.error as exc:
            print(f"[Audio] Failed to play SFX '{sound_path.name}': {exc}")

    def preload_sfx(self, identifier: Union[str, Path]) -> None:
        """Warm the cache for a frequently used SFX."""
        sound_path = self._resolve_sfx_path(identifier)
        if sound_path is None:
            return
        if sound_path in self._sfx_cache:
            return
        try:
            self._sfx_cache[sound_path] = pygame.mixer.Sound(sound_path.as_posix())
        except pygame.error as exc:
            print(f"[Audio] Failed to preload SFX '{sound_path.name}': {exc}")

    @property
    def is_muted(self) -> bool:
        return self._is_muted

    def toggle_mute(self):
        """Toggle audio mute state."""
        self._is_muted = not self._is_muted
        if not self._initialized:
            return
            
        if self._is_muted:
            pygame.mixer.music.set_volume(0.0)
        else:
            pygame.mixer.music.set_volume(self._music_volume)

    def _resolve_music_path(self, track: Union[str, Path, None]) -> Optional[Path]:
        if track is None:
            candidate = DEFAULT_MUSIC_PATH
        else:
            candidate = Path(track)
        if not candidate.exists():
            return None
        return candidate

    def _resolve_sfx_path(self, identifier: Union[str, Path]) -> Optional[Path]:
        path = Path(identifier)
        if not path.is_absolute():
            candidate = Path(SFX_DIR) / identifier
            if candidate.exists():
                path = candidate
        if not path.exists():
            return None
        return path

    @staticmethod
    def _clamp_volume(value: float) -> float:
        return max(0.0, min(1.0, value))


_DEFAULT_AUDIO: Optional[AudioManager] = None


def get_audio() -> AudioManager:
    """Return a shared AudioManager instance."""
    global _DEFAULT_AUDIO
    if _DEFAULT_AUDIO is None:
        _DEFAULT_AUDIO = AudioManager()
    return _DEFAULT_AUDIO
