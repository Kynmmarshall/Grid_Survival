from typing import Any, Dict, Optional

import pygame

from animation import SpriteAnimation, load_frames_from_spritesheet
from settings import ACTIVE_TERRAIN_THEME, TERRAIN_THEMES, WINDOW_SIZE


class AnimatedWater:
    """Terrain-edge animation (water, lava, void) controlled via settings."""

    def __init__(self):
        self.theme_name = ACTIVE_TERRAIN_THEME
        self.theme = TERRAIN_THEMES.get(self.theme_name) or {}
        self.base_config = self._get_section("base")
        self.splash_config = self._get_section("splash")

        self.animation = None
        self.rect = pygame.Rect(0, 0, WINDOW_SIZE[0], self._target_height())
        self.rect.midbottom = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1])
        self.splash_frames = None
        self.splash_animation = None
        self.splash_rect = pygame.Rect(0, 0, 0, 0)

        self._init_base_animation()
        self._init_splash_frames()

    def update(self, dt: float):
        if self.animation:
            self.animation.update(dt)
        if self.splash_animation:
            self.splash_animation.update(dt)
            if self.splash_animation.finished:
                self.splash_animation = None

    def draw(self, surface: pygame.Surface):
        if self.animation:
            surface.blit(self.animation.image, self.rect.topleft)
        if self.splash_animation:
            surface.blit(self.splash_animation.image, self.splash_rect.topleft)

    def trigger_splash(self, x_position: float):
        if not self.splash_frames:
            return
        frame_duration = 1 / 18
        if self.splash_config:
            frame_duration = self.splash_config.get("frame_duration", frame_duration)
        self.splash_animation = SpriteAnimation(
            self.splash_frames,
            frame_duration=frame_duration,
            loop=False,
        )
        self.splash_rect = self.splash_animation.image.get_rect()
        clamped_x = max(self.rect.left, min(self.rect.right, int(round(x_position))))
        self.splash_rect.midbottom = (clamped_x, self.rect.bottom)

    def surface_top(self) -> int:
        return self.rect.top

    def has_surface(self) -> bool:
        return self.animation is not None

    def _get_section(self, key: str) -> Optional[Dict[str, Any]]:
        section = self.theme.get(key)
        return section if isinstance(section, dict) else None

    def _target_height(self) -> int:
        if not self.base_config:
            return 0
        target = self.base_config.get("target_height")
        if not target or target <= 0:
            frame_size = self.base_config.get("frame_size")
            if frame_size:
                target = frame_size[1]
            else:
                target = WINDOW_SIZE[1] // 8
        return target

    def _init_base_animation(self):
        if not self.base_config:
            return
        spritesheet = self.base_config.get("spritesheet")
        if not spritesheet:
            return
        if not spritesheet.exists():
            print(f"Terrain base spritesheet not found: {spritesheet}")
            return
        frame_size = self.base_config.get("frame_size")
        if not frame_size:
            print(
                f"Terrain theme '{self.theme_name}' missing frame_size for base animation."
            )
            return
        frame_count = self.base_config.get("frame_count", 1)
        frame_duration = self.base_config.get("frame_duration", 1 / 12)
        frames = load_frames_from_spritesheet(
            spritesheet,
            frame_size[0],
            frame_size[1],
            frame_count=frame_count,
        )
        target_height = self._target_height()
        target_height = target_height if target_height > 0 else frame_size[1]
        target_size = (WINDOW_SIZE[0], target_height)
        scaled_frames = [
            pygame.transform.smoothscale(frame, target_size) for frame in frames
        ]
        self.animation = SpriteAnimation(
            scaled_frames,
            frame_duration=frame_duration,
        )
        self.rect = self.animation.image.get_rect()
        self.rect.midbottom = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1])

    def _init_splash_frames(self):
        if not self.splash_config:
            return
        spritesheet = self.splash_config.get("spritesheet")
        if not spritesheet:
            return
        if not spritesheet.exists():
            print(f"Terrain splash spritesheet not found: {spritesheet}")
            return
        frame_size = self.splash_config.get("frame_size")
        if not frame_size:
            print(
                f"Terrain theme '{self.theme_name}' missing frame_size for splash animation."
            )
            return
        frame_count = self.splash_config.get("frame_count", 1)
        splash_frames = load_frames_from_spritesheet(
            spritesheet,
            frame_size[0],
            frame_size[1],
            frame_count=frame_count,
        )
        target_size = self.splash_config.get("size", frame_size)
        self.splash_frames = [
            pygame.transform.smoothscale(frame, target_size)
            for frame in splash_frames
        ]