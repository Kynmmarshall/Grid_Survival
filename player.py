"""
player.py — Player class.

Movement model
──────────────
  • Configurable key bindings (arrows or WASD).
  • Tile-to-tile tween for horizontal movement.
  • Spacebar/W jumps: parabolic arc with PLAYER_JUMP_VEL + PLAYER_GRAVITY.
  • Gravity: when the tile underfoot disappears the player falls off-screen.

States
──────
IDLE       – standing on a tile, waiting for input.
MOVING     – sliding from one tile centre to an adjacent one.
JUMPING    – in the air (parabolic arc); can combine with horizontal tween.
FALLING    – no tile underfoot; falling downward off-screen.
ELIMINATED – has fallen completely off-screen.
"""

import pygame

from settings import (
    ISO_GRID_OFFSET_X,
    ISO_GRID_OFFSET_Y,
    ISO_TILE_H,
    ISO_TILE_W,
    PLAYER_COLOR,
    PLAYER_COLOR_2,
    PLAYER_FALL_SPEED,
    PLAYER_GRAVITY,
    PLAYER_JUMP_VEL,
    PLAYER_SIZE,
    PLAYER_SPEED,
    WINDOW_SIZE,
)
from tile import DISAPPEARED

# ── Player states ────────────────────────────────────────────────────────────
IDLE       = "idle"
MOVING     = "moving"
JUMPING    = "jumping"
FALLING    = "falling"
ELIMINATED = "eliminated"

# Key-binding presets ──────────────────────────────────────────────────────────
KEYS_ARROWS = {
    "left":  pygame.K_LEFT,
    "right": pygame.K_RIGHT,
    "up":    pygame.K_UP,
    "down":  pygame.K_DOWN,
    "jump":  pygame.K_SPACE,
}

KEYS_WASD = {
    "left":  pygame.K_a,
    "right": pygame.K_d,
    "up":    pygame.K_w,
    "down":  pygame.K_s,
    "jump":  pygame.K_LSHIFT,
}

_DIR_MAP = {
    "left":  (-1,  0),
    "right": ( 1,  0),
    "up":    ( 0, -1),
    "down":  ( 0,  1),
}


def _tile_centre(col: int, row: int) -> tuple[float, float]:
    """Return the isometric screen centre of a tile's top diamond face."""
    return (
        ISO_GRID_OFFSET_X + (col - row) * (ISO_TILE_W // 2),
        ISO_GRID_OFFSET_Y + (col + row) * (ISO_TILE_H // 2) + ISO_TILE_H // 2,
    )


class Player:
    """Single player-controlled character."""

    def __init__(self, start_col: int = 4, start_row: int = 2,
                 keys: dict | None = None, color: tuple | None = None,
                 player_id: int = 1):
        self.player_id = player_id
        self.keys = keys or KEYS_ARROWS
        self.color = color or (PLAYER_COLOR if player_id == 1 else PLAYER_COLOR_2)

        self.col = start_col
        self.row = start_row

        cx, cy = _tile_centre(self.col, self.row)
        self.x: float = cx
        self.y: float = cy

        # Tween target (horizontal movement)
        self._target_x: float = cx
        self._target_y: float = cy

        # Vertical offset for jump arc (negative = above ground)
        self._z: float = 0.0
        self._vz: float = 0.0    # vertical velocity

        self.state: str = IDLE
        self._fall_speed: float = PLAYER_FALL_SPEED

        # Survival time
        self.alive_time: float = 0.0

    # ── helpers ──────────────────────────────────────────────────────────────

    @property
    def draw_y(self) -> float:
        """Screen Y including jump offset."""
        return self.y + self._z

    @property
    def is_alive(self) -> bool:
        return self.state != ELIMINATED

    def reset(self, start_col: int = 4, start_row: int = 2) -> None:
        self.col = start_col
        self.row = start_row
        cx, cy = _tile_centre(self.col, self.row)
        self.x = cx
        self.y = cy
        self._target_x = cx
        self._target_y = cy
        self._z = 0.0
        self._vz = 0.0
        self.state = IDLE
        self._fall_speed = PLAYER_FALL_SPEED
        self.alive_time = 0.0

    # ── Input ────────────────────────────────────────────────────────────────

    def handle_input(self, keys, grid) -> None:
        if self.state in (FALLING, ELIMINATED):
            return

        # Jump — allowed from IDLE or MOVING (not already jumping)
        if keys[self.keys["jump"]] and self.state in (IDLE, MOVING):
            self._vz = PLAYER_JUMP_VEL
            self.state = JUMPING

        # Directional movement — only when IDLE (on ground, not mid-tween)
        if self.state == IDLE:
            for direction, (dcol, drow) in _DIR_MAP.items():
                if keys[self.keys[direction]]:
                    new_col = self.col + dcol
                    new_row = self.row + drow
                    target_tile = grid.get_tile(new_col, new_row)
                    if target_tile and target_tile.is_solid:
                        self.col = new_col
                        self.row = new_row
                        self._target_x, self._target_y = _tile_centre(new_col, new_row)
                        self.state = MOVING
                    break

    # ── Update ───────────────────────────────────────────────────────────────

    def update(self, dt: float, grid) -> None:
        if self.state == ELIMINATED:
            return

        self.alive_time += dt

        if self.state == JUMPING:
            self._update_jump(dt, grid)
        elif self.state == MOVING:
            self._update_tween(dt)
        elif self.state == IDLE:
            self._check_fall(grid)
        elif self.state == FALLING:
            self._update_fall(dt)

    def _update_tween(self, dt: float) -> None:
        dx = self._target_x - self.x
        dy = self._target_y - self.y
        dist = (dx * dx + dy * dy) ** 0.5
        step = PLAYER_SPEED * dt

        if dist <= step:
            self.x = self._target_x
            self.y = self._target_y
            self.state = IDLE
        else:
            self.x += dx / dist * step
            self.y += dy / dist * step

    def _update_jump(self, dt: float, grid) -> None:
        # Apply gravity to vertical velocity
        self._vz += PLAYER_GRAVITY * dt
        self._z += self._vz * dt

        # Also continue horizontal tween if one is in progress
        dx = self._target_x - self.x
        dy = self._target_y - self.y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > 1:
            step = PLAYER_SPEED * dt
            if dist <= step:
                self.x = self._target_x
                self.y = self._target_y
            else:
                self.x += dx / dist * step
                self.y += dy / dist * step

        # Landed?
        if self._z >= 0:
            self._z = 0.0
            self._vz = 0.0
            # Check if there's a tile to land on
            current_tile = grid.get_tile(self.col, self.row)
            if current_tile and current_tile.state != DISAPPEARED:
                self.state = IDLE
            else:
                self.state = FALLING

    def _check_fall(self, grid) -> None:
        current_tile = grid.get_tile(self.col, self.row)
        if current_tile is None or current_tile.state == DISAPPEARED:
            self.state = FALLING

    def _update_fall(self, dt: float) -> None:
        self._fall_speed += 600 * dt
        self.y += self._fall_speed * dt
        if self.y > WINDOW_SIZE[1] + PLAYER_SIZE:
            self.state = ELIMINATED

    # ── Draw ─────────────────────────────────────────────────────────────────

    def draw(self, surface: pygame.Surface) -> None:
        if self.state == ELIMINATED:
            return

        ix = int(self.x)
        iy = int(self.draw_y)
        hw = ISO_TILE_W // 4
        hh = ISO_TILE_H // 4

        # Shadow on the ground when jumping
        if self._z < -2:
            ground_y = int(self.y)
            shadow_pts = [
                (ix,      ground_y - hh // 2),
                (ix + hw, ground_y),
                (ix,      ground_y + hh // 2),
                (ix - hw, ground_y),
            ]
            shadow_surf = pygame.Surface(
                (hw * 2 + 2, hh + 2), pygame.SRCALPHA
            )
            local_pts = [(p[0] - ix + hw, p[1] - ground_y + hh // 2) for p in shadow_pts]
            pygame.draw.polygon(shadow_surf, (0, 0, 0, 60), local_pts)
            surface.blit(shadow_surf, (ix - hw, ground_y - hh // 2))

        pts = [
            (ix,      iy - hh),
            (ix + hw, iy),
            (ix,      iy + hh),
            (ix - hw, iy),
        ]
        pygame.draw.polygon(surface, self.color, pts)
        pygame.draw.polygon(surface, (255, 255, 255), pts, 2)
