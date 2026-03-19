"""Lightweight audio helpers for Grid Survival."""

from pathlib import Path
import pygame

from settings import ASSETS_DIR

MUSIC_PATH = ASSETS_DIR / "Audio" / "Background" / "Grid survival 1.mp3"
SFX_DIR = ASSETS_DIR / "Audio" / "sfx"


class AudioManager:
    """Centralized wrapper around pygame.mixer for music and simple SFX."""

    def __init__(self):
        self._initialized = False
        self._music_loaded = False
        self._ensure_mixer()

    def _ensure_mixer(self):
        if self._initialized:
            return
        try:
            pygame.mixer.init()
            self._initialized = True
        except pygame.error as exc:
            print(f"[Audio] Unable to initialize mixer: {exc}")

    def play_music(self, loop: bool = True, fade_ms: int = 1500):
        if not self._initialized:
            return
        if not MUSIC_PATH.exists():
            print(f"[Audio] Music file not found: {MUSIC_PATH}")
            return
        if not self._music_loaded:
            try:
                pygame.mixer.music.load(MUSIC_PATH.as_posix())
                self._music_loaded = True
            except pygame.error as exc:
                print(f"[Audio] Failed to load music: {exc}")
                return
        loops = -1 if loop else 0
        pygame.mixer.music.play(loops=loops, fade_ms=fade_ms)

    def stop_music(self, fade_ms: int = 1000):
        if not self._initialized or not pygame.mixer.music.get_busy():
            return
        if fade_ms > 0:
            pygame.mixer.music.fadeout(fade_ms)
        else:
            pygame.mixer.music.stop()

    def play_sfx(self, name: str):
        if not self._initialized:
            return
        sound_path = Path(SFX_DIR) / name
        if not sound_path.exists():
            print(f"[Audio] SFX not found: {sound_path}")
            return
        try:
            sound = pygame.mixer.Sound(sound_path.as_posix())
            sound.play()
        except pygame.error as exc:
            print(f"[Audio] Failed to play SFX '{name}': {exc}")
