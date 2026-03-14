import pygame

from animation import SpriteAnimation, load_frames_from_spritesheet
from settings import (
    WATER_FRAME_COUNT,
    WATER_FRAME_DURATION,
    WATER_FRAME_SIZE,
    WATER_SPRITESHEET,
    WATER_TARGET_HEIGHT,
    WINDOW_SIZE,
)


class AnimatedWater:
    """Animated water strip rendered along the bottom of the screen."""

    def __init__(self):
        self._active = WATER_SPRITESHEET.exists()
        if not self._active:
            print(f"Water spritesheet not found: {WATER_SPRITESHEET}")
            self.animation = None
            self.rect = pygame.Rect(0, 0, 0, 0)
            return

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

    def update(self, dt: float):
        if not self.animation:
            return
        self.animation.update(dt)

    def draw(self, surface: pygame.Surface):
        if not self.animation:
            return
        surface.blit(self.animation.image, self.rect.topleft)