"""
Magic Orb System for Grid Survival.

Magic orbs appear on the arena and grant bonuses when a player walks over them.
Five types exist, each with a distinct colour, icon, and effect:

  SPEED   (cyan)   — +50% movement speed for 8 s
  SHIELD  (gold)   — absorbs the next hazard hit
  FREEZE  (blue)   — freeze all tiles and hazards for 3 s (same as Wizard power)
  POWER   (purple) — immediately recharge all power cooldowns
  BOMB    (red)    — smash every WARNING tile on the map instantly

The OrbManager spawns orbs on random walkable positions, tracks collection,
and provides the integration hooks that GameManager calls each frame.
"""

from __future__ import annotations

import math
import random
from enum import Enum
from typing import List, Optional, Tuple

import pygame

from settings import (
    WINDOW_SIZE,
    ORB_LIFETIME,
    ORB_SHIELD_DURATION,
    ORB_FREEZE_DURATION,
    POWER_ORBS_REQUIRED,
)

W, H = WINDOW_SIZE


# ─────────────────────────────────────────────────────────────────────────────
# Orb type enum
# ─────────────────────────────────────────────────────────────────────────────

class OrbType(Enum):
    SPEED  = "speed"
    SHIELD = "shield"
    FREEZE = "freeze"
    POWER  = "power"
    BOMB   = "bomb"


# Visual config per type  (color, label, glow_color)
_ORB_VISUALS: dict[OrbType, tuple] = {
    OrbType.SPEED:  ((60, 230, 220),  "SPD", (100, 255, 245)),
    OrbType.SHIELD: ((255, 210, 50),  "SHL", (255, 240, 120)),
    OrbType.FREEZE: ((80,  140, 255), "FRZ", (140, 180, 255)),
    OrbType.POWER:  ((200, 80,  255), "POW", (230, 140, 255)),
    OrbType.BOMB:   ((255, 70,  50),  "BMB", (255, 140, 80)),
}


# ─────────────────────────────────────────────────────────────────────────────
# Individual orb
# ─────────────────────────────────────────────────────────────────────────────

class MagicOrb:
    """A collectible orb floating above the arena."""

    RADIUS = 14
    COLLECT_RADIUS = 28    # pick-up detection radius
    BOB_AMP = 5.0          # pixels of up/down float
    BOB_SPEED = 2.0        # cycles per second
    SPIN_SPEED = 90.0      # degrees per second for decoration ring

    def __init__(self, orb_type: OrbType, position: Tuple[float, float]):
        self.orb_type = orb_type
        self.position = pygame.Vector2(position)
        self._spawn_pos = pygame.Vector2(position)
        self.active = True
        self._age = 0.0
        self._spin_angle = 0.0
        self._alpha = 0           # fades in from 0 → 255
        self._collect_flash = 0.0  # >0 → play collect flash animation
        self._lifetime = ORB_LIFETIME

        color, label, glow = _ORB_VISUALS[orb_type]
        self.color = color
        self.glow_color = glow
        self.label = label

    def update(self, dt: float):
        self._age += dt
        self._spin_angle = (self._spin_angle + self.SPIN_SPEED * dt) % 360
        self._alpha = min(255, int(self._age / 0.4 * 255))   # 0.4s fade-in
        if self._collect_flash > 0:
            self._collect_flash -= dt
        self._lifetime -= dt
        if self._lifetime <= 0:
            self.active = False
        elif self._lifetime <= 2.0:
            fade = max(0.0, self._lifetime / 2.0)
            self._alpha = int(self._alpha * fade)

    def get_draw_y(self) -> float:
        """Bobbing Y position."""
        return self._spawn_pos.y + math.sin(self._age * self.BOB_SPEED * math.tau) * self.BOB_AMP

    def draw(self, surface: pygame.Surface):
        if not self.active:
            return
        cx = int(self.position.x)
        cy = int(self.get_draw_y())
        r = self.RADIUS
        alpha = self._alpha

        # Outer glow
        glow_surf = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*self.glow_color, int(alpha * 0.35)),
                           (r * 2, r * 2), r * 2)
        surface.blit(glow_surf, (cx - r * 2, cy - r * 2))

        # Core circle
        core_surf = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(core_surf, (*self.color, alpha),
                           (r + 1, r + 1), r)
        # Bright inner highlight
        pygame.draw.circle(core_surf, (255, 255, 255, int(alpha * 0.4)),
                           (r - 3, r - 3), r // 3)
        surface.blit(core_surf, (cx - r - 1, cy - r - 1))

        # Spinning decoration ring — 4 small dots orbiting
        ring_surf = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        for i in range(4):
            angle = math.radians(self._spin_angle + i * 90)
            dot_x = int(r * 2 + math.cos(angle) * (r + 6))
            dot_y = int(r * 2 + math.sin(angle) * (r + 6))
            pygame.draw.circle(ring_surf, (*self.color, int(alpha * 0.7)),
                               (dot_x, dot_y), 3)
        surface.blit(ring_surf, (cx - r * 2, cy - r * 2))

        # Type label (tiny text)
        try:
            font = pygame.font.SysFont("consolas", 9, bold=True)
            lbl = font.render(self.label, True, (255, 255, 255))
            lbl.set_alpha(alpha)
            surface.blit(lbl, lbl.get_rect(center=(cx, cy)))
        except Exception:
            pass

    def _collision_rect(self) -> pygame.Rect:
        diameter = self.COLLECT_RADIUS * 2
        rect = pygame.Rect(0, 0, diameter, diameter)
        rect.center = (round(self.position.x), round(self.position.y))
        return rect

    def check_collection(self, player) -> bool:
        """Return True if the player's hitbox overlaps this orb."""
        if not self.active:
            return False
        player_rect = player.get_hitbox() if hasattr(player, "get_hitbox") else player.rect
        return player_rect.colliderect(self._collision_rect())

    def collect(self):
        """Mark as collected and trigger flash."""
        self.active = False
        self._collect_flash = 0.3


# ─────────────────────────────────────────────────────────────────────────────
# Orb effects applied to player / game
# ─────────────────────────────────────────────────────────────────────────────

def apply_orb_effect(orb_type: OrbType, collector, game) -> str:
    """
    Apply the orb's bonus to *collector* and/or the *game* world.
    Returns a short descriptive string for the HUD notification.
    """
    if orb_type == OrbType.SPEED:
        # Temporary speed boost — store on player, game ticks it down
        collector._orb_speed_boost = 1.5
        collector._orb_speed_timer = 8.0
        if hasattr(collector, "set_active_orb"):
            collector.set_active_orb("Speed Boost", getattr(collector, "_orb_speed_timer", 8.0))
        return "SPEED BOOST  +50%"

    elif orb_type == OrbType.SHIELD:
        collector.add_shield(ORB_SHIELD_DURATION)
        if hasattr(collector, "set_active_orb"):
            remaining = getattr(collector, "_shield_timer", ORB_SHIELD_DURATION)
            collector.set_active_orb("Shield", remaining)
        return f"SHIELD {int(ORB_SHIELD_DURATION)}s of protection"

    elif orb_type == OrbType.FREEZE:
        collector.apply_freeze(ORB_FREEZE_DURATION)
        if hasattr(collector, "set_active_orb"):
            collector.set_active_orb("Frozen", ORB_FREEZE_DURATION)
        return f"FREEZE can't move for {int(ORB_FREEZE_DURATION)}s"

    elif orb_type == OrbType.POWER:
        if hasattr(collector, 'add_power_orb_charge'):
            charges = collector.add_power_orb_charge()
            if hasattr(collector, "set_active_orb"):
                collector.set_active_orb("Power Charge", None)
            return f"POWER CHARGE {charges}/{POWER_ORBS_REQUIRED}"
        return "POWER CHARGE"

    elif orb_type == OrbType.BOMB:
        # Smash every WARNING tile immediately
        from tile_system import TileState
        smashed = 0
        for tile in game.tile_manager.tiles.values():
            if tile.state == TileState.WARNING:
                tile._start_crumble()
                smashed += 1
        if hasattr(collector, "set_active_orb"):
            collector.set_active_orb("Bomb Detonation", 1.5)
        return f"BOMB  {smashed} tiles destroyed"

    return ""


# ─────────────────────────────────────────────────────────────────────────────
# Orb manager
# ─────────────────────────────────────────────────────────────────────────────

class OrbManager:
    """
    Spawns, updates, draws, and checks collection of all magic orbs.

    Spawn strategy:
      - Orbs appear on random positions within walkable_bounds
      - At most MAX_ORBS active at once
      - After an orb is collected a cooldown passes before a new one spawns
      - Orb type distribution is weighted (SPEED/SHIELD most common, BOMB rarest)
    """

    MAX_ORBS = 3
    BASE_SPAWN_INTERVAL = 8.0   # seconds between spawn attempts
    SPAWN_JITTER = 4.0          # ± random jitter on interval

    # Weighted type pool — higher count = more common
    _TYPE_POOL: list[OrbType] = (
        [OrbType.SPEED]  * 4 +
        [OrbType.SHIELD] * 3 +
        [OrbType.FREEZE] * 2 +
        [OrbType.POWER]  * 2 +
        [OrbType.BOMB]   * 1
    )

    def __init__(self, level_number: int = 1):
        self.orbs: list[MagicOrb] = []
        self._spawn_timer = 0.0
        self._next_spawn = self._roll_interval()
        self._rng = random.Random()
        self._notification: str = ""
        self._notification_timer = 0.0
        # Scale spawn frequency with level (higher level = more orbs)
        self._spawn_scale = max(0.4, 1.0 - (level_number - 1) * 0.08)

    def _roll_interval(self) -> float:
        return (self.BASE_SPAWN_INTERVAL +
                random.uniform(-self.SPAWN_JITTER, self.SPAWN_JITTER))

    def update(self, dt: float, walkable_bounds: pygame.Rect | None,
               players: list, game):
        # Tick orbs
        for orb in self.orbs:
            orb.update(dt)

        # Check collection for every active player
        for player in players:
            if getattr(player, '_eliminated', False):
                continue
            for orb in self.orbs:
                if not orb.active:
                    continue
                if orb.check_collection(player):
                    orb.collect()
                    msg = apply_orb_effect(orb.orb_type, player, game)
                    self._notification = msg
                    self._notification_timer = 2.5
                    # Play collect sound if available
                    try:
                        from audio import get_audio
                        from settings import SOUND_POWER_READY
                        get_audio().play_sfx(SOUND_POWER_READY, volume=0.7, max_instances=2)
                    except Exception:
                        pass

        # Prune inactive orbs
        self.orbs = [o for o in self.orbs if o.active]

        # Tick player orb buffs
        for player in players:
            if hasattr(player, '_orb_speed_timer'):
                player._orb_speed_timer -= dt
                if player._orb_speed_timer <= 0:
                    player._orb_speed_boost = 1.0
                    del player._orb_speed_timer

        # Notification fade
        if self._notification_timer > 0:
            self._notification_timer -= dt

        # Spawn new orbs
        self._spawn_timer += dt
        if (self._spawn_timer >= self._next_spawn and
                len(self.orbs) < self.MAX_ORBS and
                walkable_bounds is not None):
            self._spawn_timer = 0.0
            self._next_spawn = self._roll_interval() * self._spawn_scale
            self._try_spawn(walkable_bounds, getattr(game, "tile_manager", None))

    def _try_spawn(self, walkable_bounds: pygame.Rect,
                   tile_manager) -> None:
        """Spawn a new orb on an intact tile, falling back to bounds if needed."""
        spawn_pos = self._spawn_position_from_tiles(tile_manager)
        if spawn_pos is None:
            spawn_pos = self._spawn_position_from_bounds(walkable_bounds)
        if spawn_pos is None:
            return
        orb_type = self._rng.choice(self._TYPE_POOL)
        self.orbs.append(MagicOrb(orb_type, spawn_pos))

    def _spawn_position_from_tiles(self, tile_manager) -> tuple[float, float] | None:
        if not tile_manager:
            return None
        from tile_system import TileState
        viable = [
            tile for tile in tile_manager.tiles.values()
            if tile.state not in (TileState.DISAPPEARED, TileState.CRUMBLING)
        ]
        if not viable:
            return None
        tile = self._rng.choice(viable)
        cx, cy = tile._iso_center()
        jitter_x = self._rng.uniform(-tile.tile_width * 0.25, tile.tile_width * 0.25)
        jitter_y = self._rng.uniform(-tile.tile_height * 0.15, tile.tile_height * 0.05)
        return (cx + jitter_x, cy + jitter_y)

    def _spawn_position_from_bounds(self, walkable_bounds: pygame.Rect | None) -> tuple[float, float] | None:
        if walkable_bounds is None:
            return None
        padding = 40
        left = walkable_bounds.left + padding
        right = max(left + 1, walkable_bounds.right - padding)
        top = walkable_bounds.top + padding
        bottom = max(top + 1, walkable_bounds.bottom - padding)
        x = float(self._rng.randint(left, right))
        y = float(self._rng.randint(top, bottom))
        return (x, y)

    def draw(self, surface: pygame.Surface):
        for orb in self.orbs:
            orb.draw(surface)
        self._draw_notification(surface)

    def _draw_notification(self, surface: pygame.Surface):
        if not self._notification or self._notification_timer <= 0:
            return
        try:
            font = pygame.font.SysFont("consolas", 18, bold=True)
            alpha = min(255, int(self._notification_timer / 2.5 * 255))
            surf = font.render(f"  {self._notification}  ", True, (255, 240, 100))
            surf.set_alpha(alpha)
            rect = surf.get_rect(center=(W // 2, H - 130))
            # Background pill
            bg = pygame.Surface((rect.width + 16, rect.height + 8), pygame.SRCALPHA)
            bg.fill((20, 15, 40, int(alpha * 0.8)))
            pygame.draw.rect(bg, (255, 200, 50, alpha),
                             bg.get_rect(), 1, border_radius=6)
            surface.blit(bg, (rect.left - 8, rect.top - 4))
            surface.blit(surf, rect)
        except Exception:
            pass

    def reset(self):
        self.orbs.clear()
        self._spawn_timer = 0.0
        self._next_spawn = self._roll_interval()
        self._notification = ""
        self._notification_timer = 0.0