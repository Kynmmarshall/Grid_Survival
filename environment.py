"""
Procedural environment renderer for Grid Survival.

Generates a visually distinct, animated background for each of the 6 levels
entirely in code — no external image assets required.  Each environment has:
  • A multi-stop sky gradient (built from pygame Surfaces)
  • An ambient ground/horizon glow
  • Level-specific particle system (clouds, embers, dust, stars, etc.)
  • Procedural decorative shapes (mountains, crater rims, cliff silhouettes)
  • A tile colour tint applied to the isometric map surface

Usage:
    env = LevelEnvironment(level_number)          # create once per level
    env.update(dt)                                 # call every frame
    env.draw_background(screen)                    # call before map / players
    env.draw_foreground(screen)                    # call after map / players
    tinted_map = env.tint_map_surface(map_surf)   # recolour the tile map
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import pygame

from settings import WINDOW_SIZE

W, H = WINDOW_SIZE

# ─────────────────────────────────────────────────────────────────────────────
# Tiny particle used by all environments
# ─────────────────────────────────────────────────────────────────────────────

class _Particle:
    __slots__ = ('x', 'y', 'vx', 'vy', 'size', 'color', 'alpha',
                 'fade', 'lifetime', 'age', 'alive')

    def __init__(self, x, y, vx, vy, size, color, alpha=255,
                 fade=80.0, lifetime=4.0):
        self.x = x;  self.y = y
        self.vx = vx; self.vy = vy
        self.size = size
        self.color = color
        self.alpha = alpha
        self.fade = fade          # alpha units/sec to fade out
        self.lifetime = lifetime
        self.age = 0.0
        self.alive = True

    def update(self, dt):
        self.age += dt
        if self.age >= self.lifetime:
            self.alive = False
            return
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.alpha = max(0, self.alpha - self.fade * dt)

    def draw(self, surf):
        if not self.alive or self.alpha <= 0:
            return
        r = max(1, int(self.size))
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.color[:3], int(self.alpha)), (r, r), r)
        surf.blit(s, (int(self.x - r), int(self.y - r)))


# ─────────────────────────────────────────────────────────────────────────────
# Gradient helper — builds a vertical two-colour strip
# ─────────────────────────────────────────────────────────────────────────────

def _make_gradient(top_color: Tuple, bot_color: Tuple,
                   width=W, height=H) -> pygame.Surface:
    surf = pygame.Surface((width, height))
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(top_color[0] + (bot_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bot_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bot_color[2] - top_color[2]) * t)
        pygame.draw.line(surf, (r, g, b), (0, y), (width, y))
    return surf


# ─────────────────────────────────────────────────────────────────────────────
# Level-specific environments
# ─────────────────────────────────────────────────────────────────────────────

class _BaseEnv:
    """Common interface every level environment implements."""

    TILE_TINT: Tuple[int, int, int, int] = (0, 0, 0, 0)  # RGBA overlay on map

    def __init__(self):
        self._particles: List[_Particle] = []
        self._rng = random.Random()
        self._time = 0.0
        self._bg: pygame.Surface = pygame.Surface((W, H))
        self._bg.fill((18, 18, 22))
        self._build_bg()

    def _build_bg(self):
        """Override to paint self._bg once at startup."""
        pass

    def _spawn_rate(self) -> float:
        """Particles per second to spawn."""
        return 0.0

    def _make_particle(self) -> _Particle | None:
        return None

    def update(self, dt: float):
        self._time += dt
        # Spawn particles
        n = int(self._spawn_rate() * dt)
        for _ in range(n + (1 if self._rng.random() < (self._spawn_rate() * dt % 1) else 0)):
            p = self._make_particle()
            if p:
                self._particles.append(p)
        # Update and prune
        for p in self._particles:
            p.update(dt)
        self._particles = [p for p in self._particles if p.alive]

    def draw_background(self, surface: pygame.Surface):
        surface.blit(self._bg, (0, 0))
        self._draw_bg_animated(surface)

    def _draw_bg_animated(self, surface: pygame.Surface):
        """Override for animated background layers (particles drawn here)."""
        for p in self._particles:
            p.draw(surface)

    def draw_foreground(self, surface: pygame.Surface):
        """Drawn after map + players — foreground fog/embers etc."""
        pass

    def tint_map_surface(self, map_surf: pygame.Surface) -> pygame.Surface:
        """Return a copy of map_surf with the level colour tint applied."""
        if self.TILE_TINT[3] == 0:
            return map_surf
        tinted = map_surf.copy()
        r, g, b, a = self.TILE_TINT
        overlay = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
        overlay.fill((r, g, b, a))
        tinted.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT
                    if False else 0)
        tinted.blit(overlay, (0, 0))
        return tinted


# ── Level 1: Meadow ─────────────────────────────────────────────────────────

class _MeadowEnv(_BaseEnv):
    """Soft daytime sky, floating clouds, gentle grass shimmer."""

    TILE_TINT = (20, 40, 10, 18)   # slight green wash on tiles

    def _build_bg(self):
        self._bg = _make_gradient((105, 168, 238), (145, 195, 170))
        self._hill_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        pts_back = [(0, H)]
        for x in range(0, W + 40, 40):
            pts_back.append((x, H - 150 + int(55 * math.sin(x * 0.007))))
        pts_back.append((W, H))
        pygame.draw.polygon(self._hill_surf, (85, 155, 80, 170), pts_back)
        pts_front = [(0, H)]
        for x in range(0, W + 28, 28):
            pts_front.append((x, H - 72 + int(32 * math.sin(x * 0.016 + 1.5))))
        pts_front.append((W, H))
        pygame.draw.polygon(self._hill_surf, (50, 110, 55, 230), pts_front)
        pygame.draw.circle(self._hill_surf, (255, 240, 130, 210), (W - 110, 75), 44)
        pygame.draw.circle(self._hill_surf, (255, 255, 180, 70),  (W - 110, 75), 70)

    def _spawn_rate(self): return 1.2   # cloud puffs per second

    def _make_particle(self):
        # Soft white clouds drifting right-to-left
        return _Particle(
            x=self._rng.uniform(W, W + 60),
            y=self._rng.uniform(40, H // 3),
            vx=self._rng.uniform(-22, -12),
            vy=self._rng.uniform(-2, 2),
            size=self._rng.uniform(12, 32),
            color=(240, 245, 255),
            alpha=self._rng.randint(90, 150),
            fade=12.0,
            lifetime=self._rng.uniform(18, 30),
        )

    def draw_background(self, surface):
        surface.blit(self._bg, (0, 0))
        surface.blit(self._hill_surf, (0, 0))
        for p in self._particles:
            p.draw(surface)


# ── Level 2: Cliffs ─────────────────────────────────────────────────────────

class _CliffsEnv(_BaseEnv):
    """Warm sunset amber, rocky cliff silhouettes, dust motes."""

    TILE_TINT = (60, 35, 0, 22)   # warm amber wash

    def _build_bg(self):
        self._bg = _make_gradient((30, 15, 5), (180, 90, 30))
        self._cliff_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        # Layered cliff shapes from both sides
        # Left cliff
        lpts = [(0, H), (0, H//2 - 20)]
        for x in range(0, W//3 + 10, 10):
            lpts.append((x, H//2 - 20 + int(40 * math.sin(x * 0.04))))
        lpts.append((W//3, H))
        pygame.draw.polygon(self._cliff_surf, (60, 35, 15, 210), lpts)
        # Right cliff
        rpts = [(W, H), (W, H//2 - 40)]
        for x in range(W, 2*W//3 - 10, -10):
            rpts.append((x, H//2 - 40 + int(50 * math.sin(x * 0.035 + 1.0))))
        rpts.append((2*W//3, H))
        pygame.draw.polygon(self._cliff_surf, (55, 30, 12, 215), rpts)
        # Horizon glow
        glow = pygame.Surface((W, 120), pygame.SRCALPHA)
        for i in range(60):
            alpha = int(90 * (1 - i / 60))
            pygame.draw.line(glow, (255, 150, 40, alpha), (0, 60 + i), (W, 60 + i))
        self._cliff_surf.blit(glow, (0, H // 2 - 60))

    def _spawn_rate(self): return 8.0

    def _make_particle(self):
        # Dust motes rising in warm updrafts
        return _Particle(
            x=self._rng.uniform(0, W),
            y=self._rng.uniform(H//2, H),
            vx=self._rng.uniform(-8, 8),
            vy=self._rng.uniform(-25, -8),
            size=self._rng.uniform(1.5, 4),
            color=(200, 140, 70),
            alpha=self._rng.randint(60, 130),
            fade=18.0,
            lifetime=self._rng.uniform(3, 7),
        )

    def draw_background(self, surface):
        surface.blit(self._bg, (0, 0))
        surface.blit(self._cliff_surf, (0, 0))
        for p in self._particles:
            p.draw(surface)


# ── Level 3: Ruins ──────────────────────────────────────────────────────────

class _RuinsEnv(_BaseEnv):
    """Overcast grey, crumbled stone shapes, falling dust and debris."""

    TILE_TINT = (40, 35, 30, 30)   # desaturated grey-brown

    def _build_bg(self):
        self._bg = _make_gradient((55, 52, 48), (28, 26, 24))
        self._ruin_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        rng = random.Random(42)
        # Broken column stumps and wall fragments
        for _ in range(8):
            x = rng.randint(30, W - 30)
            h_r = rng.randint(40, 120)
            w_r = rng.randint(18, 40)
            y_base = H - rng.randint(0, 60)
            col = (rng.randint(70, 100), rng.randint(65, 90), rng.randint(55, 80), 180)
            pygame.draw.rect(self._ruin_surf, col,
                             (x - w_r//2, y_base - h_r, w_r, h_r), border_radius=2)
            # Broken top — jagged
            for jx in range(x - w_r//2, x + w_r//2, 5):
                jh = rng.randint(0, 15)
                pygame.draw.rect(self._ruin_surf, col,
                                 (jx, y_base - h_r - jh, 5, jh))
        # Cracked ground lines
        for _ in range(12):
            x1 = rng.randint(0, W)
            y1 = rng.randint(H//2, H)
            length = rng.randint(40, 120)
            angle = rng.uniform(-0.3, 0.3)
            x2 = int(x1 + length * math.cos(angle))
            y2 = int(y1 + length * math.sin(angle))
            pygame.draw.line(self._ruin_surf, (20, 18, 16, 160), (x1, y1), (x2, y2), 1)

    def _spawn_rate(self): return 15.0

    def _make_particle(self):
        # Stone dust falling vertically
        return _Particle(
            x=self._rng.uniform(0, W),
            y=self._rng.uniform(-10, H // 3),
            vx=self._rng.uniform(-4, 4),
            vy=self._rng.uniform(18, 55),
            size=self._rng.uniform(1, 3.5),
            color=(160, 150, 130),
            alpha=self._rng.randint(50, 110),
            fade=22.0,
            lifetime=self._rng.uniform(2, 5),
        )

    def draw_background(self, surface):
        surface.blit(self._bg, (0, 0))
        surface.blit(self._ruin_surf, (0, 0))
        for p in self._particles:
            p.draw(surface)

    def draw_foreground(self, surface):
        # Occasional foreground dust wisps
        for p in self._particles[::3]:
            if p.y > H // 2:
                p.draw(surface)


# ── Level 4: Volcano ────────────────────────────────────────────────────────

class _VolcanoEnv(_BaseEnv):
    """Deep crimson sky, molten lava pool at the bottom, rising embers."""

    TILE_TINT = (80, 20, 0, 35)   # fierce red-orange wash

    def _build_bg(self):
        self._bg = _make_gradient((18, 4, 2), (100, 22, 5))
        self._vol_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        # Volcano cone silhouette
        cone_pts = [(W//2 - 240, H), (W//2, H//2 - 30), (W//2 + 240, H)]
        pygame.draw.polygon(self._vol_surf, (35, 12, 5, 220), cone_pts)
        # Inner glow of lava at top of cone
        for r in range(50, 0, -5):
            alpha = int(120 * (1 - r / 50))
            pygame.draw.circle(self._vol_surf, (255, 120, 10, alpha),
                               (W//2, H//2 - 30), r)
        # Lava pool across bottom
        lava_pts = [(0, H)]
        for x in range(0, W + 20, 20):
            lava_pts.append((x, H - 30 + int(12 * math.sin(x * 0.025))))
        lava_pts.append((W, H))
        pygame.draw.polygon(self._vol_surf, (200, 70, 5, 230), lava_pts)
        # Lava glow
        for i in range(40):
            alpha = int(80 * (1 - i / 40))
            pygame.draw.line(self._vol_surf, (255, 100, 0, alpha),
                             (0, H - 30 - i), (W, H - 30 - i))

    def _spawn_rate(self): return 25.0

    def _make_particle(self):
        # Embers rising from lava pool
        x = self._rng.uniform(0, W)
        return _Particle(
            x=x,
            y=H - self._rng.uniform(0, 40),
            vx=self._rng.uniform(-15, 15),
            vy=self._rng.uniform(-60, -20),
            size=self._rng.uniform(1.5, 5),
            color=self._rng.choice([(255, 120, 10), (255, 60, 5), (255, 200, 50)]),
            alpha=self._rng.randint(140, 220),
            fade=40.0,
            lifetime=self._rng.uniform(1.5, 4.0),
        )

    def _draw_lava_shimmer(self, surface):
        # Animated lava shimmer at bottom
        t = self._time
        shimmer = pygame.Surface((W, 40), pygame.SRCALPHA)
        for x in range(0, W, 8):
            y = int(10 + 8 * math.sin(x * 0.04 + t * 2.5))
            alpha = int(100 + 60 * math.sin(x * 0.06 + t * 1.8))
            pygame.draw.circle(shimmer, (255, 140, 20, alpha), (x, y), 4)
        surface.blit(shimmer, (0, H - 45))

    def draw_background(self, surface):
        surface.blit(self._bg, (0, 0))
        surface.blit(self._vol_surf, (0, 0))
        for p in self._particles:
            p.draw(surface)

    def draw_foreground(self, surface):
        self._draw_lava_shimmer(surface)


# ── Level 5: Abyss ──────────────────────────────────────────────────────────

class _AbyssEnv(_BaseEnv):
    """Purple-black void, falling star streaks, deep mist."""

    TILE_TINT = (20, 0, 60, 28)   # deep purple wash

    def __init__(self):
        super().__init__()
        # Pre-generate fixed stars
        rng = random.Random(99)
        self._stars = [
            (rng.randint(0, W), rng.randint(0, H),
             rng.uniform(0.5, 2.5), rng.uniform(0, math.tau))
            for _ in range(200)
        ]

    def _build_bg(self):
        self._bg = _make_gradient((5, 2, 18), (15, 5, 40))
        self._abyss_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        # Deep void crack in the middle — yawning darkness
        crack_pts = [(W//2 - 120, H), (W//2 - 20, H//2),
                     (W//2 + 20, H//2), (W//2 + 120, H)]
        pygame.draw.polygon(self._abyss_surf, (5, 0, 15, 200), crack_pts)
        # Rim glow
        for i in range(20):
            alpha = int(60 * (1 - i / 20))
            pygame.draw.line(self._abyss_surf, (80, 30, 160, alpha),
                             (W//2 - 120 + i, H), (W//2 - 20 + i//4, H//2))
            pygame.draw.line(self._abyss_surf, (80, 30, 160, alpha),
                             (W//2 + 120 - i, H), (W//2 + 20 - i//4, H//2))

    def _spawn_rate(self): return 5.0

    def _make_particle(self):
        # Falling star streaks
        return _Particle(
            x=self._rng.uniform(0, W),
            y=self._rng.uniform(-20, 0),
            vx=self._rng.uniform(-5, 5),
            vy=self._rng.uniform(80, 200),
            size=self._rng.uniform(1, 2.5),
            color=self._rng.choice([(180, 140, 255), (140, 100, 230), (200, 180, 255)]),
            alpha=self._rng.randint(120, 200),
            fade=50.0,
            lifetime=self._rng.uniform(0.8, 2.0),
        )

    def _draw_stars(self, surface):
        t = self._time
        star_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        for x, y, size, phase in self._stars:
            twinkle = int(120 + 80 * math.sin(t * 2 + phase))
            pygame.draw.circle(star_surf, (200, 180, 255, twinkle),
                               (x, y), int(size))
        surface.blit(star_surf, (0, 0))

    def _draw_mist(self, surface):
        t = self._time
        mist = pygame.Surface((W, 200), pygame.SRCALPHA)
        for band in range(0, 200, 8):
            alpha = int(25 + 15 * math.sin(t * 0.7 + band * 0.1))
            offset = int(20 * math.sin(t * 0.3 + band * 0.05))
            pygame.draw.line(mist, (40, 10, 80, alpha),
                             (offset, band), (W + offset, band), 8)
        surface.blit(mist, (0, H - 200))

    def draw_background(self, surface):
        surface.blit(self._bg, (0, 0))
        self._draw_stars(surface)
        surface.blit(self._abyss_surf, (0, 0))
        for p in self._particles:
            p.draw(surface)

    def draw_foreground(self, surface):
        self._draw_mist(surface)


# ── Level 6: Void ───────────────────────────────────────────────────────────

class _VoidEnv(_BaseEnv):
    """Pure black space, slowly rotating galaxy spiral, electric flickers."""

    TILE_TINT = (0, 0, 0, 45)    # heavy desaturation — almost monochrome tiles

    def __init__(self):
        super().__init__()
        rng = random.Random(7)
        # Galaxy arm dots — pre-computed in polar coords
        self._galaxy = []
        for i in range(400):
            r = rng.uniform(50, 300)
            theta = rng.uniform(0, math.tau) + r * 0.018   # spiral
            sx = W//2 + int(r * math.cos(theta))
            sy = H//2 + int(r * math.sin(theta) * 0.55)   # squash vertically
            size = rng.uniform(0.5, 2.0)
            brightness = rng.randint(60, 200)
            hue_shift = int(40 * math.sin(theta * 2))
            self._galaxy.append((sx, sy, size, brightness, hue_shift))
        self._galaxy_angle = 0.0

    def _build_bg(self):
        self._bg.fill((4, 3, 8))

    def _spawn_rate(self): return 3.0

    def _make_particle(self):
        # Electric arc flickers at random positions
        return _Particle(
            x=self._rng.uniform(0, W),
            y=self._rng.uniform(0, H),
            vx=self._rng.uniform(-30, 30),
            vy=self._rng.uniform(-30, 30),
            size=self._rng.uniform(1, 3),
            color=self._rng.choice([(80, 200, 255), (150, 100, 255), (200, 255, 255)]),
            alpha=self._rng.randint(160, 255),
            fade=300.0,
            lifetime=self._rng.uniform(0.2, 0.6),
        )

    def _draw_galaxy(self, surface):
        self._galaxy_angle += 0.008
        galaxy_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        cos_a = math.cos(self._galaxy_angle)
        sin_a = math.sin(self._galaxy_angle)
        cx, cy = W//2, H//2
        for sx, sy, size, brightness, hue_shift in self._galaxy:
            # Rotate around center
            dx, dy = sx - cx, sy - cy
            rx = int(cx + dx * cos_a - dy * sin_a * 0.55)
            ry = int(cy + dx * sin_a + dy * cos_a * 0.55)
            alpha = min(255, brightness)
            r = min(255, brightness + hue_shift)
            b = min(255, brightness + 40)
            pygame.draw.circle(galaxy_surf, (r, brightness // 2, b, alpha),
                               (rx, ry), max(1, int(size)))
        # Central core glow
        for rad in range(40, 0, -5):
            alpha = int(60 * (1 - rad / 40))
            pygame.draw.circle(galaxy_surf, (200, 150, 255, alpha), (cx, cy), rad)
        surface.blit(galaxy_surf, (0, 0))

    def _draw_electric_arcs(self, surface):
        t = self._time
        arc_surf = pygame.Surface((W, H), pygame.SRCALPHA)
        rng = random.Random(int(t * 10))   # deterministic per-frame flicker
        for _ in range(3):
            if rng.random() < 0.4:
                x1 = rng.randint(0, W)
                y1 = rng.randint(H//3, 2*H//3)
                x2 = x1 + rng.randint(-80, 80)
                y2 = y1 + rng.randint(-40, 40)
                alpha = rng.randint(80, 180)
                pygame.draw.line(arc_surf, (100, 220, 255, alpha),
                                 (x1, y1), (x2, y2), 1)
        surface.blit(arc_surf, (0, 0))

    def draw_background(self, surface):
        surface.blit(self._bg, (0, 0))
        self._draw_galaxy(surface)
        for p in self._particles:
            p.draw(surface)

    def draw_foreground(self, surface):
        self._draw_electric_arcs(surface)


# ─────────────────────────────────────────────────────────────────────────────
# Public factory
# ─────────────────────────────────────────────────────────────────────────────

_ENV_CLASSES = {
    1: _MeadowEnv,
    2: _CliffsEnv,
    3: _RuinsEnv,
    4: _VolcanoEnv,
    5: _AbyssEnv,
    6: _VoidEnv,
}


def LevelEnvironment(level_number: int) -> _BaseEnv:
    """Return a fully constructed environment for *level_number* (1–6)."""
    cls = _ENV_CLASSES.get(level_number, _VoidEnv)
    return cls()
