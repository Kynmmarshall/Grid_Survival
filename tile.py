"""
tile.py — Tile class with Normal → Warning → Disappeared state machine.

State transitions
─────────────────
NORMAL     : idle, fully visible.
WARNING    : scheduled to fall — flashes amber/transparent for TILE_WARNING_TIME.
DISAPPEARED: invisible; player standing here will fall.
"""

import pygame

from settings import (
    TILE_COLOR_BORDER,
    TILE_COLOR_NORMAL,
    TILE_COLOR_VOID,
    TILE_COLOR_WARNING,
    TILE_FLASH_RATE,
    TILE_SIZE,
    TILE_WARNING_TIME,
)

# ── State constants ──────────────────────────────────────────────────────────
NORMAL      = "normal"
WARNING     = "warning"
DISAPPEARED = "disappeared"


class Tile:
    """A single grid tile with a state machine and pixel-position."""

    def __init__(self, col: int, row: int, origin_x: int, origin_y: int):
        self.col = col
        self.row = row

        # Pixel rect for drawing and collision
        self.rect = pygame.Rect(
            origin_x + col * TILE_SIZE,
            origin_y + row * TILE_SIZE,
            TILE_SIZE,
            TILE_SIZE,
        )

        self.state: str = NORMAL

        # Warning / flash state
        self._warn_timer: float = 0.0     # total time spent in WARNING
        self._flash_timer: float = 0.0    # time since last flash toggle
        self._flash_visible: bool = True  # current flash on/off

    # ── Public API ──────────────────────────────────────────────────────────

    def trigger_warning(self) -> None:
        """Move tile from NORMAL into WARNING state."""
        if self.state == NORMAL:
            self.state = WARNING
            self._warn_timer = 0.0
            self._flash_timer = 0.0
            self._flash_visible = True

    def reset(self) -> None:
        """Restore tile to NORMAL (used for respawning / new round)."""
        self.state = NORMAL
        self._warn_timer = 0.0
        self._flash_timer = 0.0
        self._flash_visible = True

    @property
    def is_solid(self) -> bool:
        return self.state != DISAPPEARED

    # ── Update ──────────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        if self.state != WARNING:
            return

        self._warn_timer  += dt
        self._flash_timer += dt

        # Increase flash speed as the countdown nears zero
        progress = max(0.0, self._warn_timer / TILE_WARNING_TIME)   # 0→1
        current_flash_rate = TILE_FLASH_RATE * (1.0 - progress * 0.75)  # speeds up

        if self._flash_timer >= current_flash_rate:
            self._flash_timer -= current_flash_rate
            self._flash_visible = not self._flash_visible

        if self._warn_timer >= TILE_WARNING_TIME:
            self.state = DISAPPEARED

    # ── Draw ────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface) -> None:
        if self.state == DISAPPEARED:
            # Draw a dark pit so the gap is visible
            pygame.draw.rect(surface, TILE_COLOR_VOID, self.rect)
            return

        if self.state == WARNING:
            if not self._flash_visible:
                # Draw semi-transparent void during "off" flash
                pygame.draw.rect(surface, TILE_COLOR_VOID, self.rect)
                return
            color = TILE_COLOR_WARNING
        else:
            color = TILE_COLOR_NORMAL

        # Filled rectangle
        pygame.draw.rect(surface, color, self.rect)
        # Border
        pygame.draw.rect(surface, TILE_COLOR_BORDER, self.rect, 2)
