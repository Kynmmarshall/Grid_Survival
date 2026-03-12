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
    ISO_TILE_DEPTH,
    ISO_TILE_H,
    ISO_TILE_W,
    TILE_BORDER_COLOR,
    TILE_COLOR_VOID,
    TILE_COLOR_WARNING,
    TILE_FLASH_RATE,
    TILE_LEFT_COLOR,
    TILE_RIGHT_COLOR,
    TILE_TOP_COLOR,
    TILE_WARNING_TIME,
)


def _shade(color: tuple, factor: float) -> tuple:
    """Return a brightened or darkened version of *color* by *factor*."""
    return tuple(min(255, max(0, int(c * factor))) for c in color[:3])

# ── State constants ──────────────────────────────────────────────────────────
NORMAL      = "normal"
WARNING     = "warning"
DISAPPEARED = "disappeared"


class Tile:
    """A single grid tile with a state machine and pixel-position."""

    def __init__(self, col: int, row: int, origin_x: int, origin_y: int):
        self.col = col
        self.row = row

        # Isometric north-vertex (topmost point of the tile's top diamond face)
        self.iso_x: int = origin_x + (col - row) * (ISO_TILE_W // 2)
        self.iso_y: int = origin_y + (col + row) * (ISO_TILE_H // 2)

        # Axis-aligned bounding rect (diamond + box face) — used for hit-testing
        self.rect = pygame.Rect(
            self.iso_x - ISO_TILE_W // 2,
            self.iso_y,
            ISO_TILE_W,
            ISO_TILE_H + ISO_TILE_DEPTH,
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
            # Dark pit — just the top diamond face to show the hole
            self._draw_top_diamond(surface, TILE_COLOR_VOID)
            return

        if self.state == WARNING:
            if not self._flash_visible:
                self._draw_top_diamond(surface, TILE_COLOR_VOID)
                return
            # Warning uses shaded amber for all faces
            warn = TILE_COLOR_WARNING
            self._draw_iso_box(surface,
                               top=warn,
                               left=_shade(warn, 0.68),
                               right=_shade(warn, 0.48),
                               border=_shade(warn, 0.30))
        else:
            self._draw_iso_box(surface,
                               top=TILE_TOP_COLOR,
                               left=TILE_LEFT_COLOR,
                               right=TILE_RIGHT_COLOR,
                               border=TILE_BORDER_COLOR)

    def _draw_iso_box(self, surface: pygame.Surface, *,
                       top: tuple, left: tuple, right: tuple,
                       border: tuple) -> None:
        """Draw a 3-D isometric box with explicit face colours and 1 px border."""
        ix, iy = self.iso_x, self.iso_y
        hw = ISO_TILE_W // 2   # 64
        hh = ISO_TILE_H // 2   # 32
        d  = ISO_TILE_DEPTH    # 32

        # ── Side faces (drawn first, beneath the top face) ────────────────
        left_pts = [
            (ix - hw, iy + hh),
            (ix,      iy + ISO_TILE_H),
            (ix,      iy + ISO_TILE_H + d),
            (ix - hw, iy + hh + d),
        ]
        pygame.draw.polygon(surface, left, left_pts)
        pygame.draw.polygon(surface, border, left_pts, 1)

        right_pts = [
            (ix + hw, iy + hh),
            (ix,      iy + ISO_TILE_H),
            (ix,      iy + ISO_TILE_H + d),
            (ix + hw, iy + hh + d),
        ]
        pygame.draw.polygon(surface, right, right_pts)
        pygame.draw.polygon(surface, border, right_pts, 1)

        # ── Top diamond face ──────────────────────────────────────────────
        top_pts = [
            (ix,      iy),               # N
            (ix + hw, iy + hh),          # E
            (ix,      iy + ISO_TILE_H),  # S
            (ix - hw, iy + hh),          # W
        ]
        pygame.draw.polygon(surface, top, top_pts)
        pygame.draw.polygon(surface, border, top_pts, 1)

    def _draw_top_diamond(self, surface: pygame.Surface, color: tuple) -> None:
        """Draw only the top diamond face (used for disappeared / void tiles)."""
        ix, iy = self.iso_x, self.iso_y
        hw = ISO_TILE_W // 2
        pts = [
            (ix,      iy),
            (ix + hw, iy + ISO_TILE_H // 2),
            (ix,      iy + ISO_TILE_H),
            (ix - hw, iy + ISO_TILE_H // 2),
        ]
        pygame.draw.polygon(surface, color, pts)
        pygame.draw.polygon(surface, _shade(color, 0.5), pts, 1)
