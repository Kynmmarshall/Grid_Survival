"""
TMX-based tile disappearance system for Grid Survival.
Manages tile states (Normal, Warning, Crumbling, Disappeared) directly on isometric TMX tiles.
Includes crumble animation, particle debris, and sound effects.
"""

import random
import math
import pygame
from enum import Enum
from typing import List, Dict, Tuple, Optional

from audio import get_audio
from settings import (
    WINDOW_SIZE,
    WALKABLE_LAYER_NAMES,
    DESTRUCTIBLE_LAYER_NAMES,
    TILE_CRUMBLE_DURATION,
    TILE_GRACE_PERIOD,
    SOUND_TILE_WARNING,
    SOUND_TILE_DISAPPEAR,
)


# ─────────────────────────────────────────────────────────────────────────────
# Debris particle
# ─────────────────────────────────────────────────────────────────────────────

class DebrisParticle:
    """Small colored square that flies outward from a crumbling tile."""

    GRAVITY = 600.0  # pixels/s²
    LIFETIME = 0.5   # seconds

    def __init__(self, x: float, y: float, color: Tuple[int, int, int]):
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(60, 180)
        self.x = x
        self.y = y
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - random.uniform(40, 120)
        self.size = random.randint(3, 7)
        self.color = color
        self.age = 0.0
        self.alive = True

    def update(self, dt: float):
        self.age += dt
        if self.age >= self.LIFETIME:
            self.alive = False
            return
        self.vy += self.GRAVITY * dt
        self.x += self.vx * dt
        self.y += self.vy * dt

    def draw(self, surface: pygame.Surface):
        if not self.alive:
            return
        alpha = int(255 * max(0.0, 1.0 - self.age / self.LIFETIME))
        s = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
        s.fill((*self.color, alpha))
        surface.blit(s, (int(self.x - self.size / 2), int(self.y - self.size / 2)))


# ─────────────────────────────────────────────────────────────────────────────
# Tile state enum
# ─────────────────────────────────────────────────────────────────────────────

class TileState(Enum):
    """Tile lifecycle states."""
    NORMAL = "normal"
    WARNING = "warning"
    CRUMBLING = "crumbling"   # NEW: visual crumble before full disappearance
    DISAPPEARED = "disappeared"


# ─────────────────────────────────────────────────────────────────────────────
# Individual tile
# ─────────────────────────────────────────────────────────────────────────────

class TMXTile:
    """Individual TMX tile with state management and visual effects."""

    def __init__(self, grid_x: int, grid_y: int, pixel_x: int, pixel_y: int,
                 tile_width: int, tile_height: int, gid: int,
                 image: Optional[pygame.Surface] = None):
        self.grid_x = grid_x
        self.grid_y = grid_y
        self.pixel_x = pixel_x
        self.pixel_y = pixel_y
        self.tile_width = tile_width
        self.tile_height = tile_height
        self.gid = gid
        self.image = image

        self.state = TileState.NORMAL
        self.warning_timer = 0.0
        self.warning_duration = 1.5   # seconds in WARNING before crumbling
        self.crumble_timer = 0.0      # time spent in CRUMBLING state
        self.flash_speed = 8.0        # flashes per second during WARNING
        self.alpha = 255

        # Debris particles spawned when crumble starts
        self.particles: List[DebrisParticle] = []

    # ── state transitions ──────────────────────────────────────────────────

    def set_warning(self):
        """Trigger warning state."""
        if self.state == TileState.NORMAL:
            self.state = TileState.WARNING
            self.warning_timer = 0.0

    def _start_crumble(self):
        """Transition from WARNING → CRUMBLING and spawn debris."""
        self.state = TileState.CRUMBLING
        self.crumble_timer = 0.0
        self.alpha = 255
        # Spawn 4–6 debris particles from the tile's iso center
        cx, cy = self._iso_center()
        for _ in range(random.randint(4, 6)):
            color = random.choice([
                (180, 120, 60),
                (140, 100, 50),
                (200, 160, 80),
                (100, 80, 40),
            ])
            self.particles.append(DebrisParticle(cx, cy, color))

    def update(self, dt: float) -> bool:
        """
        Update tile state.
        Returns True when the tile *just* fully disappeared (CRUMBLING → DISAPPEARED).
        """
        # Update debris particles regardless of state
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.alive]

        if self.state == TileState.WARNING:
            self.warning_timer += dt
            # Pulsing orange overlay alpha
            flash_cycle = (self.warning_timer * self.flash_speed) % 1.0
            self.alpha = int(100 + 155 * flash_cycle)

            if self.warning_timer >= self.warning_duration:
                self._start_crumble()

        elif self.state == TileState.CRUMBLING:
            self.crumble_timer += dt
            progress = min(1.0, self.crumble_timer / TILE_CRUMBLE_DURATION)
            # Darken progressively to black
            self.alpha = int(255 * (1.0 - progress))

            if self.crumble_timer >= TILE_CRUMBLE_DURATION:
                self.state = TileState.DISAPPEARED
                self.alpha = 0
                return True

        return False

    # ── queries ────────────────────────────────────────────────────────────

    def is_walkable(self) -> bool:
        return self.state == TileState.NORMAL

    def is_disappeared(self) -> bool:
        return self.state == TileState.DISAPPEARED

    def reset(self):
        self.state = TileState.NORMAL
        self.warning_timer = 0.0
        self.crumble_timer = 0.0
        self.alpha = 255
        self.particles.clear()

    # ── geometry helpers ───────────────────────────────────────────────────

    def _iso_center(self) -> Tuple[int, int]:
        """Return the screen-space center of the tile's top face."""
        cx = self.pixel_x + self.tile_width // 2
        cy = self.pixel_y + self.tile_height // 2
        return cx, cy

    def get_diamond_points(self) -> List[Tuple[int, int]]:
        """Get the diamond-shaped overlay points for isometric tile top face."""
        half_width = self.tile_width / 2
        half_height = self.tile_height / 2
        center_x = self.pixel_x + half_width
        top_y = self.pixel_y

        return [
            (int(center_x), int(top_y)),
            (int(center_x + half_width), int(top_y + half_height)),
            (int(center_x), int(top_y + self.tile_height)),
            (int(center_x - half_width), int(top_y + half_height)),
        ]

    # ── drawing ────────────────────────────────────────────────────────────

    def draw_warning_overlay(self, surface: pygame.Surface):
        """Draw pulsing orange overlay during WARNING state."""
        if self.state != TileState.WARNING:
            return
        points = self.get_diamond_points()
        color = (255, 150, 0, self.alpha)
        temp = pygame.Surface((self.tile_width, self.tile_height), pygame.SRCALPHA)
        adj = [(p[0] - self.pixel_x, p[1] - self.pixel_y) for p in points]
        pygame.draw.polygon(temp, color, adj)
        pygame.draw.polygon(temp, (255, 80, 0), adj, 3)
        surface.blit(temp, (self.pixel_x, self.pixel_y))

    def draw_crumble_overlay(self, surface: pygame.Surface):
        """Draw darkening overlay during CRUMBLING state."""
        if self.state != TileState.CRUMBLING:
            return
        points = self.get_diamond_points()
        # Darken from transparent to opaque black
        dark_alpha = int(255 * (1.0 - self.alpha / 255))
        color = (0, 0, 0, dark_alpha)
        temp = pygame.Surface((self.tile_width, self.tile_height), pygame.SRCALPHA)
        adj = [(p[0] - self.pixel_x, p[1] - self.pixel_y) for p in points]
        pygame.draw.polygon(temp, color, adj)
        surface.blit(temp, (self.pixel_x, self.pixel_y))

    def draw_particles(self, surface: pygame.Surface):
        """Draw debris particles."""
        for p in self.particles:
            p.draw(surface)


# ─────────────────────────────────────────────────────────────────────────────
# Tile manager
# ─────────────────────────────────────────────────────────────────────────────

class TMXTileManager:
    """
    Manages tile disappearance directly on TMX isometric tiles.
    Works with the existing TMX map data and walkable mask.
    """

    def __init__(self, tmx_data, scale_x: float = 1.0, scale_y: float = 1.0,
                 offset: Optional[Tuple[int, int]] = None):
        self.tmx_data = tmx_data
        self.scale_x = scale_x
        self.scale_y = scale_y
        if offset:
            self.offset_x, self.offset_y = offset
        else:
            self.offset_x = self.offset_y = 0
        self.tiles: Dict[Tuple[int, int], TMXTile] = {}
        self.disappeared_tiles: List[TMXTile] = []

        # Difficulty scaling parameters
        self.time_elapsed = 0.0
        self.base_disappear_interval = 3.0
        self.min_disappear_interval = 0.8
        self.difficulty_scale_rate = 0.95
        self.current_interval = self.base_disappear_interval
        self.disappear_timer = 0.0
        self.simultaneous_tiles = 1

        # Grace period before first tile disappears
        self.grace_timer = 0.0
        self.grace_period = TILE_GRACE_PERIOD

        # Audio access
        self.audio = get_audio()

        # Build tile registry from TMX data
        self._build_tile_registry()

    # ── setup ──────────────────────────────────────────────────────────────

    def _build_tile_registry(self):
        """Build registry of walkable tiles from TMX data."""
        if not self.tmx_data:
            return
        source_layers = DESTRUCTIBLE_LAYER_NAMES or WALKABLE_LAYER_NAMES
        target_layers = {name.lower() for name in source_layers}

        for layer in self.tmx_data.layers:
            if getattr(layer, "name", "").lower() not in target_layers:
                continue
            if not hasattr(layer, "tiles"):
                continue

            for x, y, gid in layer:
                if gid == 0:
                    continue
                pixel_x, pixel_y = self._tile_to_pixel(x, y, layer)
                scaled_x = int(pixel_x * self.scale_x) + self.offset_x
                scaled_y = int(pixel_y * self.scale_y) + self.offset_y
                scaled_width = int(self.tmx_data.tilewidth * self.scale_x)
                scaled_height = int(self.tmx_data.tileheight * self.scale_y)
                image = self._get_scaled_tile_image(gid)
                tile = TMXTile(x, y, scaled_x, scaled_y, scaled_width, scaled_height, gid, image)
                self.tiles[(x, y)] = tile
    def _get_scaled_tile_image(self, gid: int) -> Optional[pygame.Surface]:
        if gid == 0 or not self.tmx_data:
            return None
        image = self.tmx_data.get_tile_image_by_gid(gid)
        if image is None:
            return None
        target_width = max(1, int(round(image.get_width() * self.scale_x)))
        target_height = max(1, int(round(image.get_height() * self.scale_y)))
        if target_width == image.get_width() and target_height == image.get_height():
            return image.copy()
        return pygame.transform.smoothscale(image, (target_width, target_height))

    def _tile_to_pixel(self, x: int, y: int, layer) -> Tuple[int, int]:
        """Convert TMX grid coordinates to isometric pixel coordinates."""
        layer_offset_x = getattr(layer, "offsetx", 0)
        layer_offset_y = getattr(layer, "offsety", 0)

        if self.tmx_data.orientation == "isometric":
            half_width = self.tmx_data.tilewidth / 2
            half_height = self.tmx_data.tileheight / 2
            origin_x = self.tmx_data.height * half_width
            pixel_x = (x - y) * half_width + origin_x
            pixel_y = (x + y) * half_height
        else:
            pixel_x = x * self.tmx_data.tilewidth
            pixel_y = y * self.tmx_data.tileheight

        pixel_x += layer_offset_x
        pixel_y += layer_offset_y
        return int(round(pixel_x)), int(round(pixel_y))

    # ── update ─────────────────────────────────────────────────────────────

    def update(self, dt: float):
        """Update all tiles and handle disappearance logic."""
        self.time_elapsed += dt

        # Grace period: don't start disappearing tiles yet
        if self.grace_timer < self.grace_period:
            self.grace_timer += dt
            # Still update particles from any existing tiles
            for tile in self.tiles.values():
                tile.update(dt)
            return

        self.disappear_timer += dt

        # Update existing tiles; collect newly disappeared ones
        for tile in self.tiles.values():
            just_disappeared = tile.update(dt)
            if just_disappeared:
                self.disappeared_tiles.append(tile)
                self.audio.play_sfx(SOUND_TILE_DISAPPEAR)

        # Trigger new tile warnings based on difficulty
        if self.disappear_timer >= self.current_interval:
            self.disappear_timer = 0.0
            self._trigger_random_tiles()

            # Increase difficulty
            self.current_interval = max(
                self.min_disappear_interval,
                self.current_interval * self.difficulty_scale_rate
            )

            # Increase simultaneous tiles over time
            if self.time_elapsed > 30 and self.simultaneous_tiles < 3:
                self.simultaneous_tiles = 2
            elif self.time_elapsed > 60 and self.simultaneous_tiles < 4:
                self.simultaneous_tiles = 3

    def _trigger_random_tiles(self):
        """Select random normal tiles and set them to warning state."""
        normal_tiles = [t for t in self.tiles.values() if t.state == TileState.NORMAL]
        if not normal_tiles:
            return

        min_safe_tiles = max(3, int(len(self.tiles) * 0.3))
        if len(normal_tiles) <= min_safe_tiles:
            return

        num_to_warn = min(self.simultaneous_tiles, len(normal_tiles) - min_safe_tiles)
        tiles_to_warn = random.sample(normal_tiles, num_to_warn)

        for tile in tiles_to_warn:
            tile.set_warning()
            self.audio.play_sfx(SOUND_TILE_WARNING)

    # ── drawing ────────────────────────────────────────────────────────────

    def draw_warning_overlays(self, surface: pygame.Surface):
        """Draw warning overlays, crumble overlays, and debris particles."""
        for tile in self.tiles.values():
            if tile.state == TileState.WARNING:
                tile.draw_warning_overlay(surface)
            elif tile.state == TileState.CRUMBLING:
                tile.draw_crumble_overlay(surface)
            # Draw particles for any tile that has them (crumbling or just disappeared)
            tile.draw_particles(surface)

    def draw_active_tiles(self, surface: pygame.Surface):
        """Draw tiles that have not disappeared yet."""
        for tile in self.tiles.values():
            if tile.state == TileState.DISAPPEARED:
                continue
            if tile.image:
                surface.blit(tile.image, (tile.pixel_x, tile.pixel_y))


    # ── walkable mask ──────────────────────────────────────────────────────

    def get_updated_walkable_mask(self, original_mask: pygame.mask.Mask) -> pygame.mask.Mask:
        """
        Generate updated walkable mask with disappeared tiles removed.
        Tiles in CRUMBLING state are also removed (not walkable).
        """
        if not original_mask:
            return None

        updated_mask = original_mask.copy()

        for tile in self.tiles.values():
            if tile.state in (TileState.DISAPPEARED, TileState.CRUMBLING):
                tile_surface = pygame.Surface((tile.tile_width, tile.tile_height), pygame.SRCALPHA)
                points = [
                    (p[0] - tile.pixel_x, p[1] - tile.pixel_y)
                    for p in tile.get_diamond_points()
                ]
                pygame.draw.polygon(tile_surface, (255, 255, 255, 255), points)
                tile_mask = pygame.mask.from_surface(tile_surface)
                updated_mask.erase(tile_mask, (tile.pixel_x, tile.pixel_y))

        return updated_mask

    def should_render_tile(self, grid_x: int, grid_y: int) -> bool:
        """Check if a tile at grid position should be rendered."""
        tile = self.tiles.get((grid_x, grid_y))
        if not tile:
            return True
        return tile.state not in (TileState.DISAPPEARED,)

    # ── reset ──────────────────────────────────────────────────────────────

    def reset(self):
        """Reset all tiles to normal state."""
        for tile in self.tiles.values():
            tile.reset()
        self.disappeared_tiles.clear()
        self.time_elapsed = 0.0
        self.grace_timer = 0.0
        self.current_interval = self.base_disappear_interval
        self.disappear_timer = 0.0
        self.simultaneous_tiles = 1
