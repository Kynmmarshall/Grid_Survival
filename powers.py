"""
Character Power System for Grid Survival.

Each playable character has a unique active power triggered by the power key
(default: Q for player 1, P for player 2) plus passive stat modifiers that
are always in effect.

Design philosophy
─────────────────
• Powers are *thematic*: a Caveman smashes tiles, a Ninja dashes invisibly,
  a Wizard phases through warnings, etc.
• Every power is self-contained in its CharacterPower subclass.
• The Player holds a power instance and calls power.update(dt) / power.activate().
• GameManager calls power.apply_to_game(game) each frame so powers can affect
  tile states, hazards, other players, etc.
• Purely visual effects (particles, flashes) are rendered via power.draw(surface).

Power key binding is stored in the player controls dict under 'power'.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Optional

import pygame

from audio import get_audio
from settings import (
    SOUND_POWER_READY,
    SOUND_POWER_UNAVAILABLE,
)

if TYPE_CHECKING:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Visual helpers
# ─────────────────────────────────────────────────────────────────────────────

class _Particle:
    """Generic screen-space particle used by power effects."""

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 color: tuple, size: int, lifetime: float):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.size = size
        self.lifetime = lifetime
        self.age = 0.0
        self.alive = True

    def update(self, dt: float):
        self.age += dt
        if self.age >= self.lifetime:
            self.alive = False
            return
        self.vy += 400 * dt          # light gravity
        self.x += self.vx * dt
        self.y += self.vy * dt

    def draw(self, surface: pygame.Surface):
        if not self.alive:
            return
        alpha = int(255 * max(0.0, 1.0 - self.age / self.lifetime))
        s = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color[:3], alpha), (self.size, self.size), self.size)
        surface.blit(s, (int(self.x - self.size), int(self.y - self.size)))


def _burst(cx: float, cy: float, color: tuple, count: int = 14,
           speed_min: float = 60, speed_max: float = 200,
           size_range=(3, 7), lifetime: float = 0.55) -> list[_Particle]:
    particles = []
    for _ in range(count):
        angle = random.uniform(0, math.tau)
        speed = random.uniform(speed_min, speed_max)
        particles.append(_Particle(
            cx, cy,
            math.cos(angle) * speed,
            math.sin(angle) * speed - random.uniform(0, 80),
            color,
            random.randint(*size_range),
            random.uniform(lifetime * 0.6, lifetime),
        ))
    return particles


# ─────────────────────────────────────────────────────────────────────────────
# Base class
# ─────────────────────────────────────────────────────────────────────────────

class CharacterPower:
    """
    Abstract base for all character powers.

    Subclasses override:
        activate(player)        — called once when the key is pressed
        update(dt, player)      — called every frame
        apply_to_game(game)     — called every frame by GameManager
        draw(surface, player)   — called in the draw phase
    """

    # Human-readable name and short description shown in the HUD
    NAME: str = "No Power"
    DESCRIPTION: str = ""
    # Visual colour used for the cooldown ring and HUD icon
    COLOR: tuple = (180, 180, 180)
    # Cooldown in seconds between activations
    COOLDOWN: float = 8.0

    def __init__(self):
        self.cooldown_remaining = 0.0
        self.active = False
        self.active_timer = 0.0
        self._particles: list[_Particle] = []
        self.speed_multiplier: float = 1.0
        self.jump_multiplier: float = 1.0
        self._audio = get_audio()
        self._was_on_cooldown = False   # for "power ready" notification

    # ── public interface ───────────────────────────────────────────────────

    def try_activate(self, player) -> bool:
        """Called when the power key is pressed.  Returns True if activated."""
        if self.cooldown_remaining > 0 or self.active:
            self._audio.play_sfx(SOUND_POWER_UNAVAILABLE, volume=0.4, max_instances=1)
            return False
        self.activate(player)
        return True

    def activate(self, player):
        """Override to implement the power effect."""
        pass

    def update(self, dt: float, player):
        """Tick cooldown and particles; call _update_active if running."""
        was_cooling = self.cooldown_remaining > 0
        if self.cooldown_remaining > 0:
            self.cooldown_remaining = max(0.0, self.cooldown_remaining - dt)
            # Fire ready-chime exactly once when cooldown finishes
            if was_cooling and self.cooldown_remaining == 0.0:
                self._audio.play_sfx(SOUND_POWER_READY, volume=0.5, max_instances=1)

        for p in self._particles:
            p.update(dt)
        self._particles = [p for p in self._particles if p.alive]

        if self.active:
            self.active_timer += dt
            self._update_active(dt, player)

    def _update_active(self, dt: float, player):
        """Override to tick the active effect."""
        pass

    def apply_to_game(self, game):
        """Override to interact with GameManager each frame."""
        pass

    def draw(self, surface: pygame.Surface, player):
        """Draw particles and any visual overlay."""
        for p in self._particles:
            p.draw(surface)
        if self.active:
            self._draw_active(surface, player)

    def _draw_active(self, surface: pygame.Surface, player):
        """Override to draw the in-progress effect."""
        pass

    def draw_hud_icon(self, surface: pygame.Surface, rect: pygame.Rect):
        """Draw a small coloured circle into *rect* representing this power."""
        cx, cy = rect.center
        r = min(rect.width, rect.height) // 2 - 2
        pygame.draw.circle(surface, self.COLOR, (cx, cy), r)
        if self.cooldown_remaining > 0:
            # Grey overlay proportional to remaining cooldown
            frac = self.cooldown_remaining / self.COOLDOWN
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, int(180 * frac)))
            surface.blit(overlay, rect.topleft)
        pygame.draw.circle(surface, (255, 255, 255), (cx, cy), r, 2)

    @property
    def ready(self) -> bool:
        return self.cooldown_remaining <= 0 and not self.active

    @property
    def cooldown_fraction(self) -> float:
        """0.0 = fully charged, 1.0 = just used."""
        return self.cooldown_remaining / self.COOLDOWN if self.COOLDOWN > 0 else 0.0

    def reset(self):
        self.cooldown_remaining = 0.0
        self.active = False
        self.active_timer = 0.0
        self._particles.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Character powers
# ─────────────────────────────────────────────────────────────────────────────

class CavemanPower(CharacterPower):
    """
    GROUND SMASH — Caveman slams the ground, destroying every WARNING tile
    within a radius and sending a shockwave that pushes other players back.
    Passive: +15% movement speed (big strong legs).
    """

    NAME = "Ground Smash"
    DESCRIPTION = "Destroys nearby warning tiles · Shockwave repels enemies"
    COLOR = (200, 120, 40)
    COOLDOWN = 10.0
    SMASH_RADIUS = 180        # pixels — tiles within this range get smashed
    SHOCKWAVE_RADIUS = 220    # pixels — players within this range get pushed
    SHOCKWAVE_FORCE = 380     # pixels/s push velocity

    def __init__(self):
        super().__init__()
        self.speed_multiplier = 1.15
        self._shockwave_ring = 0.0     # expanding ring radius for visual
        self._shockwave_active = False

    def activate(self, player):
        self.active = True
        self.active_timer = 0.0
        self.cooldown_remaining = self.COOLDOWN
        self._shockwave_ring = 0.0
        self._shockwave_active = True
        from settings import SOUND_POWER_CAVEMAN
        self._audio.play_sfx(SOUND_POWER_CAVEMAN, volume=0.9, volume_jitter=0.05, max_instances=1)
        # Burst of rocky particles
        cx, cy = player.rect.centerx, player.rect.bottom
        self._particles += _burst(cx, cy, (180, 120, 50), count=20,
                                  speed_min=80, speed_max=240, lifetime=0.7)
        self._particles += _burst(cx, cy, (240, 200, 100), count=10,
                                  speed_min=40, speed_max=120, lifetime=0.5)

    def _update_active(self, dt: float, player):
        if self.active_timer > 0.6:
            self.active = False
            self._shockwave_active = False
        if self._shockwave_active:
            self._shockwave_ring += 500 * dt

    def apply_to_game(self, game):
        if not self.active or self.active_timer > 0.05:
            return
        # Find the player that owns this power
        owner = self._find_owner(game)
        if owner is None:
            return

        cx, cy = owner.rect.centerx, owner.rect.centery

        # Smash nearby warning tiles immediately
        from tile_system import TileState
        for tile in game.tile_manager.tiles.values():
            if tile.state != TileState.WARNING:
                continue
            tx, ty = tile._iso_center()
            dist = math.hypot(tx - cx, ty - cy)
            if dist <= self.SMASH_RADIUS:
                tile._start_crumble()

        # Push other players
        for player in game.players:
            if player in game.eliminated_players:
                continue
            if not hasattr(player, 'power') or player.power is not self:
                dx = player.position.x - cx
                dy = player.position.y - cy
                dist = math.hypot(dx, dy)
                if 0 < dist <= self.SHOCKWAVE_RADIUS:
                    scale = 1.0 - dist / self.SHOCKWAVE_RADIUS
                    push_x = (dx / dist) * self.SHOCKWAVE_FORCE * scale
                    push_y = (dy / dist) * self.SHOCKWAVE_FORCE * scale
                    player.position.x += push_x * 0.016
                    player.position.y += push_y * 0.016

    def _draw_active(self, surface: pygame.Surface, player):
        if not self._shockwave_active:
            return
        cx, cy = player.rect.centerx, player.rect.centery
        r = int(self._shockwave_ring)
        if r > 0:
            alpha = max(0, int(200 * (1.0 - self._shockwave_ring / self.SHOCKWAVE_RADIUS)))
            ring_surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(ring_surf, (*self.COLOR, alpha), (r + 2, r + 2), r, 4)
            surface.blit(ring_surf, (cx - r - 2, cy - r - 2))

    def _find_owner(self, game):
        for p in game.players:
            if hasattr(p, 'power') and p.power is self:
                return p
        return None


class NinjaPower(CharacterPower):
    """
    SHADOW DASH — Ninja blinks forward in their facing direction, becoming
    briefly invisible and passing through hazards.
    Passive: +25% movement speed.
    """

    NAME = "Shadow Dash"
    DESCRIPTION = "Blink forward · Brief invisibility · Dodge hazards"
    COLOR = (80, 200, 220)
    COOLDOWN = 6.0
    DASH_DISTANCE = 200      # pixels
    INVISIBLE_DURATION = 1.2  # seconds of ghosted state

    def __init__(self):
        super().__init__()
        self.speed_multiplier = 1.25
        self._invisible = False
        self._ghost_alpha = 255

    def activate(self, player):
        self.active = True
        self.active_timer = 0.0
        self.cooldown_remaining = self.COOLDOWN
        self._invisible = True
        self._ghost_alpha = 60
        from settings import SOUND_POWER_NINJA_DASH
        self._audio.play_sfx(SOUND_POWER_NINJA_DASH, volume=0.75, volume_jitter=0.05, max_instances=1)
        facing_vec = {
            "right": pygame.Vector2(1, 0),
            "left":  pygame.Vector2(-1, 0),
            "down":  pygame.Vector2(0, 1),
            "up":    pygame.Vector2(0, -1),
        }.get(player.facing, pygame.Vector2(1, 0))

        player.position += facing_vec * self.DASH_DISTANCE

        # Shadow-smoke trail particles at origin
        cx = player.rect.centerx - int(facing_vec.x * self.DASH_DISTANCE)
        cy = player.rect.centery - int(facing_vec.y * self.DASH_DISTANCE)
        self._particles += _burst(cx, cy, (40, 180, 200), count=18,
                                  speed_min=30, speed_max=140, lifetime=0.5)
        # Also at landing spot
        self._particles += _burst(player.rect.centerx, player.rect.centery,
                                  (120, 230, 255), count=12,
                                  speed_min=20, speed_max=100, lifetime=0.4)

    def _update_active(self, dt: float, player):
        if self.active_timer > self.INVISIBLE_DURATION:
            if self._invisible:   # fire sound exactly once on transition
                from settings import SOUND_POWER_NINJA_END
                self._audio.play_sfx(SOUND_POWER_NINJA_END, volume=0.55, max_instances=1)
            self.active = False
            self._invisible = False
            self._ghost_alpha = 255
            player._power_alpha = 255
        else:
            # Fade back in during second half of duration
            fade_start = self.INVISIBLE_DURATION * 0.5
            if self.active_timer > fade_start:
                t = (self.active_timer - fade_start) / (self.INVISIBLE_DURATION - fade_start)
                self._ghost_alpha = int(60 + 195 * t)
            player._power_alpha = self._ghost_alpha

    def apply_to_game(self, game):
        # While invisible, skip hazard collision for the owner
        if not self._invisible:
            return
        owner = self._find_owner(game)
        if owner:
            owner._immune_to_hazards = True

    def _find_owner(self, game):
        for p in game.players:
            if hasattr(p, 'power') and p.power is self:
                return p
        return None


class WizardPower(CharacterPower):
    """
    ARCANE FREEZE — Wizard freezes time for 3 seconds: tiles stop counting
    down and hazards are paused.
    Passive: Slightly slower movement (old and wise), but higher jump.
    """

    NAME = "Arcane Freeze"
    DESCRIPTION = "Freeze all tiles & hazards for 3 seconds"
    COLOR = (130, 80, 220)
    COOLDOWN = 14.0
    FREEZE_DURATION = 3.0

    def __init__(self):
        super().__init__()
        self.speed_multiplier = 0.90
        self.jump_multiplier = 1.20
        self._freeze_timer = 0.0
        self._snowflakes: list[_Particle] = []

    def activate(self, player):
        self.active = True
        self.active_timer = 0.0
        self.cooldown_remaining = self.COOLDOWN
        self._freeze_timer = self.FREEZE_DURATION
        from settings import SOUND_POWER_WIZARD
        self._audio.play_sfx(SOUND_POWER_WIZARD, volume=0.8, max_instances=1)

        cx, cy = player.rect.centerx, player.rect.centery
        # Ice-blue star burst
        self._particles += _burst(cx, cy, (140, 200, 255), count=24,
                                  speed_min=60, speed_max=280,
                                  size_range=(4, 9), lifetime=0.8)
        self._particles += _burst(cx, cy, (220, 240, 255), count=12,
                                  speed_min=20, speed_max=100, lifetime=0.6)

    def _update_active(self, dt: float, player):
        self._freeze_timer -= dt
        if self._freeze_timer <= 0:
            self.active = False
            from settings import SOUND_POWER_WIZARD_END
            self._audio.play_sfx(SOUND_POWER_WIZARD_END, volume=0.55, max_instances=1)

    def apply_to_game(self, game):
        if not self.active:
            return
        # Pause tile manager timers by undoing dt each frame;
        # we accomplish this simply by temporarily zeroing the elapsed time
        # that was just added.  The neatest hook is to subtract from timers.
        game.tile_manager.disappear_timer = max(
            0.0, game.tile_manager.disappear_timer - 0.016
        )
        # Freeze tile warning timers
        from tile_system import TileState
        for tile in game.tile_manager.tiles.values():
            if tile.state == TileState.WARNING:
                tile.warning_timer = max(0.0, tile.warning_timer - 0.016)

        # Slow bullets to a crawl
        for bullet in game.hazard_manager.bullets:
            bullet.speed = max(10, bullet.speed * 0.5)

    def _draw_active(self, surface: pygame.Surface, player):
        # Pale blue full-screen tint
        tint = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        alpha = int(30 * (self._freeze_timer / self.FREEZE_DURATION))
        tint.fill((140, 180, 255, alpha))
        surface.blit(tint, (0, 0))


class KnightPower(CharacterPower):
    """
    SHIELD BASH — Knight raises an impenetrable shield for 2 seconds
    (hazards are deflected) then slams it forward, smashing the first tile
    in the facing direction.
    Passive: +20% movement speed (heavy armour training).
    """

    NAME = "Shield Bash"
    DESCRIPTION = "Block all hazards · Slam tiles in facing direction"
    COLOR = (200, 180, 60)
    COOLDOWN = 9.0
    BLOCK_DURATION = 2.0
    BASH_RANGE = 120         # pixels ahead for tile smash

    def __init__(self):
        super().__init__()
        self.speed_multiplier = 1.20
        self._bashed = False   # has the forward smash been executed yet

    def activate(self, player):
        self.active = True
        self.active_timer = 0.0
        self.cooldown_remaining = self.COOLDOWN
        self._bashed = False
        from settings import SOUND_POWER_KNIGHT
        self._audio.play_sfx(SOUND_POWER_KNIGHT, volume=0.85, volume_jitter=0.05, max_instances=1)

        cx, cy = player.rect.centerx, player.rect.centery
        self._particles += _burst(cx, cy, (220, 200, 60), count=16,
                                  speed_min=50, speed_max=180, lifetime=0.5)
        self._particles += _burst(cx, cy, (255, 240, 140), count=8,
                                  speed_min=20, speed_max=80, lifetime=0.35)

    def _update_active(self, dt: float, player):
        if self.active_timer > self.BLOCK_DURATION:
            self.active = False

    def apply_to_game(self, game):
        owner = self._find_owner(game)
        if owner is None:
            return

        # Block hazards while shielding
        if self.active:
            owner._immune_to_hazards = True

        # Bash the nearest tile in facing direction once at start
        if not self._bashed and self.active and self.active_timer < 0.1:
            self._bashed = True
            facing_vec = {
                "right": pygame.Vector2(1, 0),
                "left":  pygame.Vector2(-1, 0),
                "down":  pygame.Vector2(0, 1),
                "up":    pygame.Vector2(0, -1),
            }.get(owner.facing, pygame.Vector2(0, 1))

            target = owner.position + facing_vec * self.BASH_RANGE
            from tile_system import TileState
            closest = None
            closest_dist = float('inf')
            for tile in game.tile_manager.tiles.values():
                if tile.state == TileState.DISAPPEARED:
                    continue
                tx, ty = tile._iso_center()
                dist = math.hypot(tx - target.x, ty - target.y)
                if dist < closest_dist:
                    closest_dist = dist
                    closest = tile
            if closest and closest_dist < 80:
                closest._start_crumble()
                from settings import SOUND_POWER_KNIGHT_BASH
                self._audio.play_sfx(SOUND_POWER_KNIGHT_BASH, volume=0.8, max_instances=1)

    def _draw_active(self, surface: pygame.Surface, player):
        # Draw a golden shield outline around the player
        r = max(player.rect.width, player.rect.height) // 2 + 8
        cx, cy = player.rect.center
        alpha = int(160 * (1.0 - self.active_timer / self.BLOCK_DURATION))
        shield_surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(shield_surf, (*self.COLOR, alpha), (r + 2, r + 2), r, 5)
        surface.blit(shield_surf, (cx - r - 2, cy - r - 2))

    def _find_owner(self, game):
        for p in game.players:
            if hasattr(p, 'power') and p.power is self:
                return p
        return None


class RobotPower(CharacterPower):
    """
    OVERCLOCK — Robot enters overdrive for 2.5 seconds: movement speed
    doubles and the jump is amplified.  Leaves an electric trail.
    Passive: Normal speed but ignores the first hazard hit per life
    (armour plating).
    """

    NAME = "Overclock"
    DESCRIPTION = "2× speed & boosted jump · Electric trail"
    COLOR = (60, 220, 180)
    COOLDOWN = 11.0
    BOOST_DURATION = 2.5
    SPEED_BOOST = 2.0
    JUMP_BOOST = 1.4

    def __init__(self):
        super().__init__()
        self._armour_intact = True      # passive one-hit protection
        self._trail_timer = 0.0

    def activate(self, player):
        self.active = True
        self.active_timer = 0.0
        self.cooldown_remaining = self.COOLDOWN
        # Boost speed and jump via temp multipliers stored on player
        player._power_speed_boost = self.SPEED_BOOST
        player._power_jump_boost = self.JUMP_BOOST
        from settings import SOUND_POWER_ROBOT
        self._audio.play_sfx(SOUND_POWER_ROBOT, volume=0.8, max_instances=1)

        cx, cy = player.rect.centerx, player.rect.centery
        self._particles += _burst(cx, cy, (60, 255, 200), count=20,
                                  speed_min=80, speed_max=260, lifetime=0.55)

    def _update_active(self, dt: float, player):
        self._trail_timer += dt
        if self._trail_timer > 0.08:
            self._trail_timer = 0.0
            self._particles += _burst(
                player.rect.centerx, player.rect.centery,
                (60, 255, 200), count=4,
                speed_min=20, speed_max=60,
                size_range=(2, 5), lifetime=0.3,
            )
        if self.active_timer > self.BOOST_DURATION:
            self.active = False
            player._power_speed_boost = 1.0
            player._power_jump_boost = 1.0

    def apply_to_game(self, game):
        # Armour passive: absorb the first hazard hit
        if not self._armour_intact:
            return
        owner = self._find_owner(game)
        if owner:
            owner._immune_to_hazards = True

    def _draw_active(self, surface: pygame.Surface, player):
        # Cyan electric glow behind the player
        cx, cy = player.rect.center
        glow_r = player.rect.width // 2 + 12
        t = self.active_timer / self.BOOST_DURATION
        alpha = int(80 * (1.0 - abs(math.sin(self.active_timer * 10))))
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(glow_surf, (*self.COLOR, alpha), (glow_r, glow_r), glow_r)
        surface.blit(glow_surf, (cx - glow_r, cy - glow_r))

    def _find_owner(self, game):
        for p in game.players:
            if hasattr(p, 'power') and p.power is self:
                return p
        return None

    def on_hazard_hit(self) -> bool:
        """Called by game when a hazard would eliminate the robot.
        Returns True if the hit was absorbed (armour still intact)."""
        if self._armour_intact:
            self._armour_intact = False
            from settings import SOUND_POWER_ROBOT_HIT
            self._audio.play_sfx(SOUND_POWER_ROBOT_HIT, volume=0.85, max_instances=1)
            return True    # absorbed — don't eliminate
        return False


class SamuraiPower(CharacterPower):
    """
    BLADE STORM — Samurai spins rapidly, deflecting all bullets in a
    wide radius for 1.5 s and sending out slashing waves that accelerate
    tile crumbling on tiles beneath enemies.
    Passive: +10% speed, +15% jump height.
    """

    NAME = "Blade Storm"
    DESCRIPTION = "Deflect bullets · Accelerate enemy tiles"
    COLOR = (220, 60, 60)
    COOLDOWN = 10.0
    DEFLECT_RADIUS = 160
    STORM_DURATION = 1.5

    def __init__(self):
        super().__init__()
        self.speed_multiplier = 1.10
        self.jump_multiplier = 1.15
        self._spin_angle = 0.0

    def activate(self, player):
        self.active = True
        self.active_timer = 0.0
        self.cooldown_remaining = self.COOLDOWN
        self._spin_angle = 0.0
        from settings import SOUND_POWER_SAMURAI
        self._audio.play_sfx(SOUND_POWER_SAMURAI, volume=0.85, volume_jitter=0.04, max_instances=1)

        cx, cy = player.rect.centerx, player.rect.centery
        self._particles += _burst(cx, cy, (220, 60, 60), count=20,
                                  speed_min=100, speed_max=300,
                                  size_range=(3, 7), lifetime=0.6)
        self._particles += _burst(cx, cy, (255, 200, 80), count=10,
                                  speed_min=40, speed_max=150, lifetime=0.4)

    def _update_active(self, dt: float, player):
        self._spin_angle += 720 * dt      # two full rotations per second
        if self.active_timer > self.STORM_DURATION:
            self.active = False

    def apply_to_game(self, game):
        if not self.active:
            return
        owner = self._find_owner(game)
        if owner is None:
            return

        cx, cy = owner.rect.centerx, owner.rect.centery

        # Deflect (deactivate) bullets within radius
        for bullet in game.hazard_manager.bullets:
            if not bullet.active:
                continue
            dist = math.hypot(bullet.position.x - cx, bullet.position.y - cy)
            if dist <= self.DEFLECT_RADIUS:
                bullet.active = False
                self._particles += _burst(
                    bullet.position.x, bullet.position.y,
                    (220, 60, 60), count=6,
                    speed_min=40, speed_max=120, lifetime=0.3,
                )

        # Accelerate warning timers on tiles under enemy players
        from tile_system import TileState
        for other in game.players:
            if other is owner or other in game.eliminated_players:
                continue
            ex, ey = other.rect.centerx, other.rect.centery
            for tile in game.tile_manager.tiles.values():
                if tile.state == TileState.NORMAL:
                    tx, ty = tile._iso_center()
                    if math.hypot(tx - ex, ty - ey) < 60:
                        tile.set_warning()
                elif tile.state == TileState.WARNING:
                    tx, ty = tile._iso_center()
                    if math.hypot(tx - ex, ty - ey) < 60:
                        tile.warning_timer += 0.05     # speed up countdown

    def _draw_active(self, surface: pygame.Surface, player):
        # Rotating red arc lines
        cx, cy = player.rect.center
        r = self.DEFLECT_RADIUS
        for i in range(4):
            angle = math.radians(self._spin_angle + i * 90)
            x1 = cx + math.cos(angle) * (r * 0.4)
            y1 = cy + math.sin(angle) * (r * 0.4)
            x2 = cx + math.cos(angle) * r
            y2 = cy + math.sin(angle) * r
            alpha = 180
            line_surf = pygame.Surface((surface.get_width(), surface.get_height()), pygame.SRCALPHA)
            pygame.draw.line(line_surf, (*self.COLOR, alpha), (int(x1), int(y1)), (int(x2), int(y2)), 3)
            surface.blit(line_surf, (0, 0))

    def _find_owner(self, game):
        for p in game.players:
            if hasattr(p, 'power') and p.power is self:
                return p
        return None


class ArcherPower(CharacterPower):
    """
    VOLLEY — Archer fires three rapid arrows that destroy WARNING tiles and
    eliminate moving traps on contact.
    Passive: +20% movement speed (light and nimble).
    """

    NAME = "Volley"
    DESCRIPTION = "Fire 3 arrows · Destroy warning tiles & traps"
    COLOR = (100, 200, 80)
    COOLDOWN = 7.0
    ARROW_SPEED = 500
    ARROW_LIFETIME = 1.5

    def __init__(self):
        super().__init__()
        self.speed_multiplier = 1.20
        self._arrows: list[dict] = []   # {pos, dir, lifetime}

    def activate(self, player):
        self.active = True
        self.active_timer = 0.0
        self.cooldown_remaining = self.COOLDOWN

        facing_vec = {
            "right": pygame.Vector2(1, 0),
            "left":  pygame.Vector2(-1, 0),
            "down":  pygame.Vector2(0, 1),
            "up":    pygame.Vector2(0, -1),
        }.get(player.facing, pygame.Vector2(1, 0))

        # Fan of three arrows
        for spread in (-15, 0, 15):
            angle = math.atan2(facing_vec.y, facing_vec.x) + math.radians(spread)
            direction = pygame.Vector2(math.cos(angle), math.sin(angle))
            self._arrows.append({
                "pos": pygame.Vector2(player.position),
                "dir": direction,
                "lifetime": self.ARROW_LIFETIME,
            })

        cx, cy = player.rect.centerx, player.rect.centery
        self._particles += _burst(cx, cy, (100, 220, 80), count=12,
                                  speed_min=40, speed_max=160, lifetime=0.4)
        from settings import SOUND_POWER_ARCHER
        self._audio.play_sfx(SOUND_POWER_ARCHER, volume=0.8, max_instances=1)

    def _update_active(self, dt: float, player):
        for arrow in self._arrows:
            arrow["lifetime"] -= dt
        self._arrows = [a for a in self._arrows if a["lifetime"] > 0]
        if not self._arrows:
            self.active = False

    def apply_to_game(self, game):
        from tile_system import TileState
        from settings import SOUND_POWER_ARROW_HIT
        for arrow in self._arrows:
            ax, ay = arrow["pos"]

            # Hit warning tiles
            for tile in game.tile_manager.tiles.values():
                if tile.state != TileState.WARNING:
                    continue
                tx, ty = tile._iso_center()
                if math.hypot(tx - ax, ty - ay) < 35:
                    tile._start_crumble()
                    self._audio.play_sfx(SOUND_POWER_ARROW_HIT, volume=0.65,
                                         volume_jitter=0.08, max_instances=3)
                    self._particles += _burst(ax, ay, (100, 220, 80), count=6,
                                              speed_min=30, speed_max=100,
                                              lifetime=0.3)

            # Destroy moving traps
            for trap in game.hazard_manager.traps:
                if not trap.active:
                    continue
                if math.hypot(trap.position.x - ax, trap.position.y - ay) < trap.size // 2 + 5:
                    trap.active = False
                    self._audio.play_sfx(SOUND_POWER_ARROW_HIT, volume=0.7,
                                         volume_jitter=0.06, max_instances=3)
                    self._particles += _burst(ax, ay, (255, 200, 80), count=8,
                                              speed_min=40, speed_max=140,
                                              lifetime=0.4)

    def _draw_active(self, surface: pygame.Surface, player):
        for arrow in self._arrows:
            ax, ay = int(arrow["pos"].x), int(arrow["pos"].y)
            dx, dy = arrow["dir"].x, arrow["dir"].y
            # Draw arrow as a thick line with a tip circle
            tail_x = int(ax - dx * 18)
            tail_y = int(ay - dy * 18)
            arrow_surf = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
            pygame.draw.line(arrow_surf, (140, 100, 40, 230), (tail_x, tail_y), (ax, ay), 3)
            pygame.draw.circle(arrow_surf, (220, 220, 60, 230), (ax, ay), 4)
            surface.blit(arrow_surf, (0, 0))


# ─────────────────────────────────────────────────────────────────────────────
# Registry: maps character name keywords → power class
# ─────────────────────────────────────────────────────────────────────────────

# Keys are lowercase substrings that may appear in the character folder name.
# First match wins, so put more specific names before generic ones.
_POWER_REGISTRY: list[tuple[str, type]] = [
    ("ninja",    NinjaPower),
    ("samurai",  SamuraiPower),
    ("knight",   KnightPower),
    ("wizard",   WizardPower),
    ("mage",     WizardPower),
    ("witch",    WizardPower),
    ("robot",    RobotPower),
    ("cyborg",   RobotPower),
    ("android",  RobotPower),
    ("archer",   ArcherPower),
    ("ranger",   ArcherPower),
    ("hunter",   ArcherPower),
    ("cave",     CavemanPower),   # matches "caveman", "cavewoman", "cave"
    ("primit",   CavemanPower),   # matches "primitive"
    ("barbarian",CavemanPower),
]

# Fallback when no keyword matches
_DEFAULT_POWER = CavemanPower


def get_power_for_character(character_name: str) -> CharacterPower:
    """Return an instantiated power appropriate for *character_name*."""
    lower = (character_name or "").lower()
    for keyword, power_cls in _POWER_REGISTRY:
        if keyword in lower:
            return power_cls()
    return _DEFAULT_POWER()


def power_key_for_player(player_index: int) -> int:
    """Return the pygame key constant for the power button of the given player slot."""
    # Player 1 → Q,  Player 2 → P,  Player 3 → comma,  Player 4 → slash
    defaults = [pygame.K_q, pygame.K_p, pygame.K_COMMA, pygame.K_SLASH]
    if 0 <= player_index < len(defaults):
        return defaults[player_index]
    return pygame.K_q