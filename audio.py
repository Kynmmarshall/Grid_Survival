"""Centralized audio management for Grid Survival."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Sequence, Union
import random

import pygame

from settings import ASSETS_DIR, MUSIC_PATH, MUSIC_VOLUME

DEFAULT_MUSIC_PATH = MUSIC_PATH
SFX_DIR = ASSETS_DIR / "sounds"


class AudioManager:
    """Centralized wrapper around pygame.mixer for music and SFX."""

    def __init__(self):
        self._initialized = False
        self._current_music: Optional[Path] = None
        self._playlist_tracks: list[Path] = []
        self._playlist_index = -1
        self._playlist_loop = True
        self._playlist_fade_ms = 1500
        self._sfx_cache: Dict[Path, pygame.mixer.Sound] = {}
        self._is_muted = False
        self._music_volume = MUSIC_VOLUME
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
        if not self._initialized or self._is_muted:
            return

        music_path = self._resolve_music_path(track)
        if music_path is None:
            print(f"[Audio] Music file not found: {track}")
            return

        self._clear_playlist_state()

        try:
            self._play_music_path(
                music_path,
                loop=loop,
                fade_ms=fade_ms,
                volume=volume,
                restart=restart,
            )
        except pygame.error as exc:
            print(f"[Audio] Failed to play music '{music_path}': {exc}")

    def play_music_playlist(
        self,
        tracks: Sequence[Union[str, Path]],
        *,
        start_random: bool = True,
        loop: bool = True,
        fade_ms: int = 1500,
        volume: Optional[float] = None,
    ):
        self._ensure_mixer()
        if not self._initialized or self._is_muted:
            return

        resolved_tracks = [self._resolve_music_path(track) for track in tracks]
        resolved_tracks = [track for track in resolved_tracks if track is not None]
        if not resolved_tracks:
            print("[Audio] No valid music tracks found for playlist.")
            return

        self._playlist_tracks = resolved_tracks
        self._playlist_loop = loop
        self._playlist_fade_ms = max(0, fade_ms)
        self._playlist_index = random.randrange(len(self._playlist_tracks)) if start_random else 0
        self._clear_current_music_state()

        try:
            self._play_music_path(
                self._playlist_tracks[self._playlist_index],
                loop=False,
                fade_ms=fade_ms,
                volume=volume,
                restart=True,
            )
        except pygame.error as exc:
            print(f"[Audio] Failed to start music playlist: {exc}")

    def update(self):
        """Advance playlist playback when a queued track finishes."""
        if not self._initialized or self._is_muted:
            return
        if not self._playlist_tracks:
            return
        if pygame.mixer.music.get_busy():
            return
        self._advance_playlist()

    def stop_music(self, fade_ms: int = 1000):
        self._ensure_mixer()
        self._clear_playlist_state()
        if not self._initialized:
            return
        if pygame.mixer.music.get_busy():
            if fade_ms > 0:
                pygame.mixer.music.fadeout(fade_ms)
            else:
                pygame.mixer.music.stop()

    def play_sfx(
        self,
        identifier: Union[str, Path],
        *,
        volume: float = 1.0,
        cache: bool = True,
        volume_jitter: float = 0.0,
        max_instances: Optional[int] = None,
    ):
        self._ensure_mixer()
        if not self._initialized or self._is_muted:
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
            if max_instances is not None and max_instances > 0:
                if sound.get_num_channels() >= max_instances:
                    return
            channel = sound.play()
            if channel is not None:
                vol = volume
                if volume_jitter > 0:
                    jitter = random.uniform(-abs(volume_jitter), abs(volume_jitter))
                    vol += jitter
                channel.set_volume(self._clamp_volume(vol * self._music_volume))
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

    def get_volume(self) -> float:
        return self._music_volume

    def set_volume(self, value: float) -> float:
        self._music_volume = self._clamp_volume(value)
        if self._initialized and not self._is_muted:
            pygame.mixer.music.set_volume(self._music_volume)
        return self._music_volume

    def adjust_volume(self, delta: float) -> float:
        return self.set_volume(self._music_volume + delta)

    def _play_music_path(
        self,
        music_path: Path,
        *,
        loop: bool,
        fade_ms: int,
        volume: Optional[float],
        restart: bool,
    ):
        if restart or self._current_music != music_path:
            pygame.mixer.music.load(music_path.as_posix())
            self._current_music = music_path

        if volume is not None:
            self._music_volume = self._clamp_volume(volume)

        effective_vol = 0.0 if self._is_muted else self._music_volume
        pygame.mixer.music.set_volume(effective_vol)

        loops = -1 if loop else 0
        pygame.mixer.music.play(loops=loops, fade_ms=max(0, fade_ms))

    def _advance_playlist(self):
        if not self._playlist_tracks:
            return

        next_index = self._playlist_index + 1
        if next_index >= len(self._playlist_tracks):
            if not self._playlist_loop:
                self._clear_playlist_state()
                return
            next_index = 0

        self._playlist_index = next_index
        try:
            self._play_music_path(
                self._playlist_tracks[self._playlist_index],
                loop=False,
                fade_ms=self._playlist_fade_ms,
                volume=None,
                restart=True,
            )
        except pygame.error as exc:
            print(f"[Audio] Failed to advance music playlist: {exc}")

    def _clear_current_music_state(self):
        self._current_music = None

    def _clear_playlist_state(self):
        self._playlist_tracks = []
        self._playlist_index = -1
        self._playlist_loop = True
        self._playlist_fade_ms = 1500

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
