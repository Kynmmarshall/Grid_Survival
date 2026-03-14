"""
hazards.py — Bullet and Trap hazards for Week 2.

Bullets:  Fly in straight lines across the grid (random edge → opposite edge).
Traps:    Bounce along tile rows/cols; occupy a tile and eliminate on contact.

Both hazard types kill any player they overlap with (by checking grid col/row).
"""

import random
from typing import Optional

import pygame

from settings import (
    BULLET_COLOR,
    BULLET_SIZE,
    BULLET_SPAWN_TIME,
    BULLET_SPEED,
    GRID_COLS,
    GRID_ROWS,
    ISO_GRID_OFFSET_X,
    ISO_GRID_OFFSET_Y,
    ISO_TILE_H,
    ISO_TILE_W,
    TRAP_COLOR,
    TRAP_SIZE,
    TRAP_SPAWN_TIME,
    TRAP_SPEED,
    WINDOW_SIZE,
)
from player import ELIMINATED, JUMPING


def _tile_centre(col: int, row: int) -> tuple[float, float]:
    """Screen centre of a tile's top diamond face."""
    return (
        ISO_GRID_OFFSET_X + (col - row) * (ISO_TILE_W // 2),
        ISO_GRID_OFFSET_Y + (col + row) * (ISO_TILE_H // 2) + ISO_TILE_H // 2,
    )


# ── Bullet ───────────────────────────────────────────────────────────────────

class Bullet:
    """A projectile that flies from one grid edge to the opposite."""

    def __init__(self, start_col: int, start_row: int,
                 dcol: int, drow: int):
        self.col_f: float = float(start_col)
        self.row_f: float = float(start_row)
        self.dcol = dcol
        self.drow = drow
        self.alive = True
        self._update_screen_pos()

    def _update_screen_pos(self):
        self.x, self.y = _tile_centre(self.col_f, self.row_f)

    @property
    def grid_col(self) -> int:
        return int(round(self.col_f))

    @property
    def grid_row(self) -> int:
        return int(round(self.row_f))

    def update(self, dt: float):
        speed = BULLET_SPEED / ((ISO_TILE_W + ISO_TILE_H) / 2)  # tiles/s
        self.col_f += self.dcol * speed * dt
        self.row_f += self.drow * speed * dt
        self._update_screen_pos()

        # Kill when fully off-grid
        if (self.col_f < -1 or self.col_f > GRID_COLS
                or self.row_f < -1 or self.row_f > GRID_ROWS):
            self.alive = False

    def draw(self, surface: pygame.Surface):
        ix, iy = int(self.x), int(self.y)
        r = BULLET_SIZE
        pts = [
            (ix, iy - r),
            (ix + r, iy),
            (ix, iy + r),
            (ix - r, iy),
        ]
        pygame.draw.polygon(surface, BULLET_COLOR, pts)
        pygame.draw.polygon(surface, (255, 255, 255), pts, 1)


# ── Trap ─────────────────────────────────────────────────────────────────────

class Trap:
    """A hazard that moves along a row or column, bouncing at edges."""

    def __init__(self, col: int, row: int, dcol: int, drow: int):
        self.col_f: float = float(col)
        self.row_f: float = float(row)
        self.dcol = dcol
        self.drow = drow
        self.alive = True
        self._lifetime: float = 0.0
        self._max_lifetime: float = 20.0  # auto-remove after 20 s
        self._update_screen_pos()

    def _update_screen_pos(self):
        self.x, self.y = _tile_centre(self.col_f, self.row_f)

    @property
    def grid_col(self) -> int:
        return int(round(self.col_f))

    @property
    def grid_row(self) -> int:
        return int(round(self.row_f))

    def update(self, dt: float):
        speed = TRAP_SPEED / ((ISO_TILE_W + ISO_TILE_H) / 2)
        self.col_f += self.dcol * speed * dt
        self.row_f += self.drow * speed * dt

        # Bounce at grid edges
        if self.col_f <= 0:
            self.col_f = 0
            self.dcol = abs(self.dcol)
        elif self.col_f >= GRID_COLS - 1:
            self.col_f = GRID_COLS - 1
            self.dcol = -abs(self.dcol)

        if self.row_f <= 0:
            self.row_f = 0
            self.drow = abs(self.drow)
        elif self.row_f >= GRID_ROWS - 1:
            self.row_f = GRID_ROWS - 1
            self.drow = -abs(self.drow)

        self._update_screen_pos()
        self._lifetime += dt
        if self._lifetime >= self._max_lifetime:
            self.alive = False

    def draw(self, surface: pygame.Surface):
        ix, iy = int(self.x), int(self.y)
        s = TRAP_SIZE
        pts = [
            (ix, iy - s),
            (ix + s, iy),
            (ix, iy + s),
            (ix - s, iy),
        ]
        pygame.draw.polygon(surface, TRAP_COLOR, pts)
        pygame.draw.polygon(surface, (255, 200, 255), pts, 1)


# ── HazardManager ────────────────────────────────────────────────────────────

class HazardManager:
    """Spawns and manages all active hazards."""

    def __init__(self, grid):
        self.grid = grid
        self.bullets: list[Bullet] = []
        self.traps: list[Trap] = []
        self._bullet_timer: float = 0.0
        self._trap_timer: float = 0.0
        self._bullet_interval: float = BULLET_SPAWN_TIME
        self._trap_interval: float = TRAP_SPAWN_TIME

    def reset(self):
        self.bullets.clear()
        self.traps.clear()
        self._bullet_timer = 0.0
        self._trap_timer = 0.0
        self._bullet_interval = BULLET_SPAWN_TIME
        self._trap_interval = TRAP_SPAWN_TIME

    # ── Spawning ─────────────────────────────────────────────────────────

    def _spawn_bullet(self):
        """Spawn a bullet from a random grid edge aimed inward."""
        side = random.choice(["top", "bottom", "left", "right"])
        if side == "top":
            col = random.randint(0, GRID_COLS - 1)
            self.bullets.append(Bullet(col, -1, 0, 1))
        elif side == "bottom":
            col = random.randint(0, GRID_COLS - 1)
            self.bullets.append(Bullet(col, GRID_ROWS, 0, -1))
        elif side == "left":
            row = random.randint(0, GRID_ROWS - 1)
            self.bullets.append(Bullet(-1, row, 1, 0))
        else:
            row = random.randint(0, GRID_ROWS - 1)
            self.bullets.append(Bullet(GRID_COLS, row, -1, 0))

    def _spawn_trap(self):
        """Spawn a trap at a random edge tile moving along its axis."""
        if random.random() < 0.5:
            # Horizontal trap
            row = random.randint(0, GRID_ROWS - 1)
            col = 0 if random.random() < 0.5 else GRID_COLS - 1
            dcol = 1 if col == 0 else -1
            self.traps.append(Trap(col, row, dcol, 0))
        else:
            # Vertical trap
            col = random.randint(0, GRID_COLS - 1)
            row = 0 if random.random() < 0.5 else GRID_ROWS - 1
            drow = 1 if row == 0 else -1
            self.traps.append(Trap(col, row, 0, drow))

    # ── Collision ────────────────────────────────────────────────────────

    def _check_collisions(self, players):
        """Eliminate any player standing on the same tile as a hazard."""
        for player in players:
            if player.state in (ELIMINATED,):
                continue
            # Jumping players are above hazards — immune
            if player.state == JUMPING:
                continue
            for bullet in self.bullets:
                if (bullet.alive
                        and bullet.grid_col == player.col
                        and bullet.grid_row == player.row):
                    player.state = ELIMINATED
            for trap in self.traps:
                if (trap.alive
                        and trap.grid_col == player.col
                        and trap.grid_row == player.row):
                    player.state = ELIMINATED

    # ── Update / Draw ────────────────────────────────────────────────────

    def update(self, dt: float, players):
        # Spawn timers
        self._bullet_timer += dt
        if self._bullet_timer >= self._bullet_interval:
            self._bullet_timer -= self._bullet_interval
            self._spawn_bullet()

        self._trap_timer += dt
        if self._trap_timer >= self._trap_interval:
            self._trap_timer -= self._trap_interval
            self._spawn_trap()

        # Update all hazards
        for b in self.bullets:
            b.update(dt)
        for t in self.traps:
            t.update(dt)

        # Remove dead
        self.bullets = [b for b in self.bullets if b.alive]
        self.traps = [t for t in self.traps if t.alive]

        self._check_collisions(players)

    def draw(self, surface: pygame.Surface):
        for b in self.bullets:
            b.draw(surface)
        for t in self.traps:
            t.draw(surface)
