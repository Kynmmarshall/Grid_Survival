import pygame

from animation import SpriteAnimation, load_frames_from_spritesheet
from settings import (
    WATER_FRAME_COUNT,
    WATER_FRAME_DURATION,
    WATER_FRAME_SIZE,
    WATER_SPLASH_FRAME_COUNT,
    WATER_SPLASH_FRAME_DURATION,
    WATER_SPLASH_FRAME_SIZE,
    WATER_SPLASH_SIZE,
    WATER_SPLASH_SPRITESHEET,
    WATER_SPRITESHEET,
    WATER_TARGET_HEIGHT,
    WINDOW_SIZE,
)


class AnimatedWater:
    """Animated water strip rendered along the bottom of the screen."""

    def __init__(self):
        self._active = WATER_SPRITESHEET.exists()
        self.animation = None
        self.rect = pygame.Rect(0, 0, WINDOW_SIZE[0], WATER_TARGET_HEIGHT)
        self.splash_frames = None
        self.splash_animation = None
        self.splash_rect = pygame.Rect(0, 0, 0, 0)

        if not self._active:
            print(f"Water spritesheet not found: {WATER_SPRITESHEET}")
        else:
            self._init_base_animation()

        if WATER_SPLASH_SPRITESHEET.exists():
            splash_frames = load_frames_from_spritesheet(
                WATER_SPLASH_SPRITESHEET,
                WATER_SPLASH_FRAME_SIZE[0],
                WATER_SPLASH_FRAME_SIZE[1],
                frame_count=WATER_SPLASH_FRAME_COUNT,
            )
            self.splash_frames = [
                pygame.transform.smoothscale(frame, WATER_SPLASH_SIZE)
                for frame in splash_frames
            ]
        else:
            print(f"Water splash spritesheet not found: {WATER_SPLASH_SPRITESHEET}")

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
        self.splash_animation = SpriteAnimation(
            self.splash_frames,
            frame_duration=WATER_SPLASH_FRAME_DURATION,
            loop=False,
        )
        self.splash_rect = self.splash_animation.image.get_rect()
        clamped_x = max(self.rect.left, min(self.rect.right, int(round(x_position))))
        self.splash_rect.midbottom = (clamped_x, self.rect.bottom)

    def surface_top(self) -> int:
        return self.rect.top

    def has_surface(self) -> bool:
        return self.animation is not None

    def _init_base_animation(self):
        frames = load_frames_from_spritesheet(
            WATER_SPRITESHEET,
            WATER_FRAME_SIZE[0],
            WATER_FRAME_SIZE[1],
            frame_count=WATER_FRAME_COUNT,
        )
        target_size = (WINDOW_SIZE[0], WATER_TARGET_HEIGHT)
        scaled_frames = [
            pygame.transform.smoothscale(frame, target_size) for frame in frames
        ]
        self.animation = SpriteAnimation(
            scaled_frames, frame_duration=WATER_FRAME_DURATION
        )
        self.rect = self.animation.image.get_rect()
        self.rect.midbottom = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1])