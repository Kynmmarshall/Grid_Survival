"""
tile_grid.py — TileGrid class.

Manages the 10×6 grid of Tile objects, schedules random disappearances,
and provides helper queries (tile at column/row, tile under a pixel rect).
"""

import random
from typing import Optional

import pygame

from settings import (
    GRID_COLS,
    GRID_ROWS,
    ISO_GRID_OFFSET_X,
    ISO_GRID_OFFSET_Y,
    TILES_PER_SECOND,
)
from tile import DISAPPEARED, NORMAL, Tile


class TileGrid:
    """Owns and updates the full tile grid."""

    def __init__(self):
        # 2-D list: self.tiles[row][col]
        self.tiles: list[list[Tile]] = [
            [
                Tile(col, row, ISO_GRID_OFFSET_X, ISO_GRID_OFFSET_Y)
                for col in range(GRID_COLS)
            ]
            for row in range(GRID_ROWS)
        ]

        # Timer that counts up; triggers a warning every (1/TILES_PER_SECOND) s
        self._spawn_timer: float = 0.0
        self._spawn_interval: float = 1.0 / TILES_PER_SECOND

    # ── Helpers ─────────────────────────────────────────────────────────────

    def get_tile(self, col: int, row: int) -> Optional[Tile]:
        """Return the Tile at (col, row), or None if out of bounds."""
        if 0 <= col < GRID_COLS and 0 <= row < GRID_ROWS:
            return self.tiles[row][col]
        return None

    def tile_at_pixel(self, x: int, y: int) -> Optional[Tile]:
        """Return the tile whose rect contains pixel (x, y)."""
        for row in self.tiles:
            for tile in row:
                if tile.rect.collidepoint(x, y):
                    return tile
        return None

    def tile_below_rect(self, rect: pygame.Rect) -> Optional[Tile]:
        """
        Return the first solid tile whose top edge is directly below `rect`.
        Used for landing/collision: checks the pixel one step below centre.
        """
        check_x = rect.centerx
        check_y = rect.bottom + 1
        return self.tile_at_pixel(check_x, check_y)

    def reset(self) -> None:
        """Restore all tiles to NORMAL for a new round."""
        for row in self.tiles:
            for tile in row:
                tile.reset()
        self._spawn_timer = 0.0

    def normal_tiles(self) -> list[Tile]:
        """Return all tiles currently in NORMAL state."""
        return [
            tile
            for row in self.tiles
            for tile in row
            if tile.state == NORMAL
        ]

    # ── Difficulty setter (called by GameManager in Week 2) ─────────────────

    def set_spawn_interval(self, interval: float) -> None:
        self._spawn_interval = max(0.1, interval)

    # ── Core update ─────────────────────────────────────────────────────────

    def _schedule_random_warning(self) -> None:
        """Pick a random NORMAL tile and put it into WARNING."""
        candidates = self.normal_tiles()
        if candidates:
            tile = random.choice(candidates)
            tile.trigger_warning()

    def update(self, dt: float) -> None:
        # Update every tile
        for row in self.tiles:
            for tile in row:
                tile.update(dt)

        # Schedule new tile warning
        self._spawn_timer += dt
        if self._spawn_timer >= self._spawn_interval:
            self._spawn_timer -= self._spawn_interval
            self._schedule_random_warning()

    # ── Draw ────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface) -> None:
        # Painter's algorithm: back-to-front by ascending (col + row) depth sum
        all_tiles = sorted(
            (tile for row in self.tiles for tile in row),
            key=lambda t: t.col + t.row,
        )
        for tile in all_tiles:
            tile.draw(surface)
