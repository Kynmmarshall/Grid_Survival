"""Character projectile combat system for Grid Survival.

Each character fires a unique themed projectile when the shoot key is pressed.
Projectiles knock back other players and destroy monsters on contact.
They do NOT directly eliminate players — knockback may cause them to fall.
"""

from __future__ import annotations

import math
import random
from enum import Enum, auto

import pygame

from audio import get_audio


# ─────────────────────────────────────────────────────────────────────────────
# Projectile kind definitions
# ─────────────────────────────────────────────────────────────────────────────

class ProjectileKind(Enum):
    ROCK = auto()
    BOULDER = auto()
    SHURIKEN = auto()
    AXE = auto()
    ENERGY_BOLT = auto()
    ICE_SHARD = auto()
    ENERGY_BULLET = auto()
    SWORD_WAVE = auto()
    ARROW = auto()


_KIND_SETTINGS: dict[ProjectileKind, dict] = {
    ProjectileKind.ROCK: {
        "speed": 220, "radius": 12, "color": (160, 120, 70),
        "glow": (210, 170, 110), "knockback": 360,
        "cooldown": 1.0, "lifetime": 2.0, "pierce": False,
        "spread_count": 1, "spread_deg": 0,
    },
    ProjectileKind.BOULDER: {
        "speed": 160, "radius": 18, "color": (130, 100, 60),
        "glow": (180, 140, 90), "knockback": 500,
        "cooldown": 2.0, "lifetime": 2.0, "pierce": False,
        "spread_count": 1, "spread_deg": 0,
    },
    ProjectileKind.SHURIKEN: {
        "speed": 320, "radius": 7, "color": (190, 200, 220),
        "glow": (140, 200, 255), "knockback": 180,
        "cooldown": 3.5, "lifetime": 1.2, "pierce": False,
        "spread_count": 2, "spread_deg": 14,
    },
    ProjectileKind.AXE: {
        "speed": 320, "radius": 10, "color": (200, 170, 80),
        "glow": (255, 220, 100), "knockback": 320,
        "cooldown": 2.0, "lifetime": 1.2, "pierce": False,
        "spread_count": 1, "spread_deg": 0,
    },
    ProjectileKind.ENERGY_BOLT: {
        "speed": 460, "radius": 8, "color": (255, 120, 30),
        "glow": (255, 180, 60), "knockback": 240,
        "cooldown": 1.8, "lifetime": 1.5, "pierce": True,
        "spread_count": 1, "spread_deg": 0,
    },
    ProjectileKind.ICE_SHARD: {
        "speed": 290, "radius": 9, "color": (140, 210, 255),
        "glow": (200, 240, 255), "knockback": 200,
        "cooldown": 2.0, "lifetime": 1.6, "pierce": False,
        "spread_count": 1, "spread_deg": 0,
        "freeze_on_hit": 0.8,
    },
    ProjectileKind.ENERGY_BULLET: {
        "speed": 580, "radius": 5, "color": (60, 230, 180),
        "glow": (100, 255, 220), "knockback": 160,
        "cooldown": 1.0, "lifetime": 1.0, "pierce": False,
        "spread_count": 1, "spread_deg": 0,
    },
    ProjectileKind.SWORD_WAVE: {
        "speed": 400, "radius": 10, "color": (220, 60, 60),
        "glow": (255, 120, 80), "knockback": 280,
        "cooldown": 1.5, "lifetime": 0.8, "pierce": False,
        "spread_count": 3, "spread_deg": 18,
    },
    ProjectileKind.ARROW: {
        "speed": 530, "radius": 6, "color": (180, 150, 80),
        "glow": (220, 200, 120), "knockback": 220,
        "cooldown": 1.8, "lifetime": 1.4, "pierce": False,
        "spread_count": 1, "spread_deg": 0,
    },
}


def _get_kind_for_character(character_name: str) -> ProjectileKind:
    lower = (character_name or "").lower()
    if "goblin" in lower:
        return ProjectileKind.BOULDER
    if "ninja" in lower:
        return ProjectileKind.SHURIKEN
    if "samurai" in lower:
        return ProjectileKind.SWORD_WAVE
    if "archer" in lower or "ranger" in lower or "hunter" in lower:
        return ProjectileKind.ARROW
    if "wizard" in lower or "mage" in lower or "witch" in lower:
        return ProjectileKind.ICE_SHARD
    if "robot" in lower or "cyborg" in lower or "android" in lower:
        return ProjectileKind.ENERGY_BULLET
    if "knight" in lower or "viking" in lower:
        return ProjectileKind.AXE
    if "dread" in lower:
        return ProjectileKind.ENERGY_BOLT
    if "cave" in lower or "primit" in lower or "barbarian" in lower:
        return ProjectileKind.ROCK
    return ProjectileKind.ROCK


# ─────────────────────────────────────────────────────────────────────────────
# Projectile entity
# ─────────────────────────────────────────────────────────────────────────────

class Projectile:
    def __init__(
        self,
        position: pygame.Vector2,
        direction: pygame.Vector2,
        kind: ProjectileKind,
        owner,
        replica: bool = False,
    ):
        cfg = _KIND_SETTINGS[kind]
        self.position = position.copy()
        self.velocity = direction.normalize() * cfg["speed"]
        self.kind = kind
        self.owner = owner
        self.radius = cfg["radius"]
        self.color = cfg["color"]
        self.glow_color = cfg["glow"]
        self.knockback = cfg["knockback"]
        self.pierce = cfg.get("pierce", False)
        self.freeze_on_hit = cfg.get("freeze_on_hit", 0.0)
        self.lifetime = cfg["lifetime"]
        self.age = 0.0
        self.alive = True
        self._spin = 0.0
        self._hit_players: set[int] = set()
        self.replica = bool(replica)

    def update(self, dt: float) -> None:
        if not self.alive:
            return
        self.age += dt
        if self.age >= self.lifetime:
            self.alive = False
            return
        self._spin += dt * 540
        self.position += self.velocity * dt

    @classmethod
    def from_snapshot(cls, data: dict) -> "Projectile":
        """Create a visual-only projectile from a snapshot dict.

        Expected keys: x, y, vx, vy, kind, age, lifetime
        """
        kind_name = str(data.get("kind", "ROCK"))
        try:
            kind = ProjectileKind[kind_name]
        except Exception:
            kind = ProjectileKind.ROCK
        pos = pygame.Vector2(float(data.get("x", 0.0)), float(data.get("y", 0.0)))
        vel = pygame.Vector2(float(data.get("vx", 0.0)), float(data.get("vy", 0.0)))
        # Build a dummy direction vector from velocity (magnitude not important)
        dir_vec = vel.normalize() if vel.length_squared() > 0 else pygame.Vector2(1, 0)
        proj = cls(pos, dir_vec, kind, owner=None, replica=True)
        proj.velocity = vel
        proj.age = float(data.get("age", 0.0))
        proj.lifetime = float(data.get("lifetime", proj.lifetime))
        return proj

    def draw(self, surface: pygame.Surface) -> None:
        if not self.alive:
            return
        px, py = int(self.position.x), int(self.position.y)
        r = self.radius
        alpha_frac = max(0.0, 1.0 - self.age / self.lifetime)
        alpha = int(255 * alpha_frac)

        glow_r = r * 3
        glow_surf = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            glow_surf, (*self.glow_color, int(80 * alpha_frac)),
            (glow_r, glow_r), glow_r,
        )
        surface.blit(glow_surf, (px - glow_r, py - glow_r))

        if self.kind == ProjectileKind.SHURIKEN:
            self._draw_shuriken(surface, px, py, r, alpha)
        elif self.kind == ProjectileKind.AXE:
            self._draw_axe(surface, px, py, r, alpha)
        elif self.kind == ProjectileKind.ARROW:
            self._draw_arrow(surface, px, py, r, alpha)
        elif self.kind in (ProjectileKind.ENERGY_BOLT, ProjectileKind.ENERGY_BULLET):
            self._draw_energy(surface, px, py, r, alpha)
        elif self.kind == ProjectileKind.SWORD_WAVE:
            self._draw_sword_wave(surface, px, py, r, alpha)
        else:
            proj_surf = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            pygame.draw.circle(proj_surf, (*self.color, alpha), (r + 1, r + 1), r)
            pygame.draw.circle(proj_surf, (*self.glow_color, min(255, alpha + 40)), (r + 1, r + 1), r, 2)
            surface.blit(proj_surf, (px - r - 1, py - r - 1))

    def _draw_shuriken(self, surface: pygame.Surface, px: int, py: int, r: int, alpha: int) -> None:
        angle_rad = math.radians(self._spin)
        sz = r * 5
        s = pygame.Surface((sz, sz), pygame.SRCALPHA)
        cx = cy = sz // 2
        for i in range(4):
            a = angle_rad + i * math.pi / 2
            pts = [
                (cx + math.cos(a) * r * 2.2, cy + math.sin(a) * r * 2.2),
                (cx + math.cos(a + 1.1) * r * 0.7, cy + math.sin(a + 1.1) * r * 0.7),
                (cx + math.cos(a - 1.1) * r * 0.7, cy + math.sin(a - 1.1) * r * 0.7),
            ]
            pygame.draw.polygon(s, (*self.color, alpha), pts)
        pygame.draw.circle(s, (*self.glow_color, alpha), (cx, cy), max(1, r - 1))
        surface.blit(s, (px - sz // 2, py - sz // 2))

    def _draw_axe(self, surface: pygame.Surface, px: int, py: int, r: int, alpha: int) -> None:
        angle_rad = math.radians(self._spin)
        sz = r * 6
        s = pygame.Surface((sz, sz), pygame.SRCALPHA)
        cx = cy = sz // 2
        blade_tip = (cx + math.cos(angle_rad) * r * 2.5, cy + math.sin(angle_rad) * r * 2.5)
        blade_l = (cx + math.cos(angle_rad + 2.0) * r, cy + math.sin(angle_rad + 2.0) * r)
        blade_r = (cx + math.cos(angle_rad - 2.0) * r, cy + math.sin(angle_rad - 2.0) * r)
        pygame.draw.polygon(s, (*self.color, alpha), [blade_tip, blade_l, blade_r])
        hx = int(cx + math.cos(angle_rad + math.pi) * r * 2.0)
        hy = int(cy + math.sin(angle_rad + math.pi) * r * 2.0)
        pygame.draw.line(s, (140, 100, 60, alpha), (cx, cy), (hx, hy), 3)
        surface.blit(s, (px - sz // 2, py - sz // 2))

    def _draw_arrow(self, surface: pygame.Surface, px: int, py: int, r: int, alpha: int) -> None:
        vx, vy = self.velocity.x, self.velocity.y
        length = math.hypot(vx, vy)
        if length < 1:
            return
        nx, ny = vx / length, vy / length
        shaft_len = r * 5
        sz = int(shaft_len + r * 4)
        s = pygame.Surface((sz * 2, sz * 2), pygame.SRCALPHA)
        mid = sz
        tail = (int(mid - nx * shaft_len), int(mid - ny * shaft_len))
        tip = (mid, mid)
        pygame.draw.line(s, (*self.color, alpha), tail, tip, 3)
        pygame.draw.circle(s, (*self.glow_color, alpha), tip, r)
        surface.blit(s, (px - mid, py - mid))

    def _draw_energy(self, surface: pygame.Surface, px: int, py: int, r: int, alpha: int) -> None:
        pulse = 0.7 + 0.3 * math.sin(self.age * 20)
        er = max(2, int(r * pulse))
        sz = er * 6
        s = pygame.Surface((sz, sz), pygame.SRCALPHA)
        cx = cy = sz // 2
        pygame.draw.circle(s, (*self.glow_color, int(140 * alpha / 255)), (cx, cy), er * 2)
        pygame.draw.circle(s, (*self.color, alpha), (cx, cy), er)
        surface.blit(s, (px - sz // 2, py - sz // 2))

    def _draw_sword_wave(self, surface: pygame.Surface, px: int, py: int, r: int, alpha: int) -> None:
        vx, vy = self.velocity.x, self.velocity.y
        length = math.hypot(vx, vy)
        if length < 1:
            return
        nx, ny = vx / length, vy / length
        perp_x, perp_y = -ny, nx
        span = r * 6
        sz = span * 2 + 20
        s = pygame.Surface((int(sz), int(sz)), pygame.SRCALPHA)
        mid = sz // 2
        pts: list[tuple[int, int]] = []
        for i in range(10):
            t = (i / 9.0) * 2 - 1
            wx = mid + perp_x * t * span + nx * math.sin(t * math.pi) * r * 2
            wy = mid + perp_y * t * span + ny * math.sin(t * math.pi) * r * 2
            pts.append((int(wx), int(wy)))
        if len(pts) >= 2:
            pygame.draw.lines(s, (*self.color, alpha), False, pts, 3)
        pygame.draw.circle(s, (*self.glow_color, int(alpha * 0.7)), (int(mid), int(mid)), r)
        surface.blit(s, (px - int(mid), py - int(mid)))


# ─────────────────────────────────────────────────────────────────────────────
# Projectile manager
# ─────────────────────────────────────────────────────────────────────────────

class ProjectileManager:
    """Manages all in-flight projectiles across all players."""

    def __init__(self) -> None:
        self._projectiles: list[Projectile] = []
        self._shoot_cooldowns: dict[int, float] = {}
        self._cooldown_owners: dict[int, object] = {}
        self._audio = get_audio()

    @staticmethod
    def _effective_cooldown(cfg: dict) -> float:
        cooldown = float(cfg.get("cooldown", 0.0))
        if int(cfg.get("spread_count", 1)) == 2:
            cooldown *= 2.0
        return max(0.0, cooldown)

    @staticmethod
    def _set_owner_projectile_charge(owner, remaining: float, total: float) -> None:
        try:
            setattr(owner, "projectile_cooldown_remaining", max(0.0, float(remaining)))
            setattr(owner, "projectile_cooldown_total", max(0.0, float(total)))
        except Exception:
            pass

    def fire(self, owner, direction: pygame.Vector2 | None = None) -> bool:
        """Fire projectile(s) from owner in their facing direction.

        Returns True if at least one projectile was spawned.
        """
        if direction is None or direction.length_squared() == 0:
            facing = getattr(owner, "facing", "right")
            direction = {
                "right": pygame.Vector2(1, 0),
                "left": pygame.Vector2(-1, 0),
                "down": pygame.Vector2(0, 1),
                "up": pygame.Vector2(0, -1),
            }.get(facing, pygame.Vector2(1, 0))

        owner_id = id(owner)
        if self._shoot_cooldowns.get(owner_id, 0.0) > 0:
            return False

        character_name = getattr(owner, "character_name", "")
        kind = _get_kind_for_character(character_name)
        cfg = _KIND_SETTINGS[kind]
        count = cfg["spread_count"]
        spread_deg = cfg["spread_deg"]
        cooldown = self._effective_cooldown(cfg)
        self._shoot_cooldowns[owner_id] = cooldown
        self._cooldown_owners[owner_id] = owner
        self._set_owner_projectile_charge(owner, cooldown, cooldown)

        rect = getattr(owner, "rect", None)
        center = pygame.Vector2(
            rect.centerx if rect else 0,
            rect.centery if rect else 0,
        )
        spawn_offset = 26
        origin = center + direction.normalize() * spawn_offset

        base_angle = math.degrees(math.atan2(direction.y, direction.x))
        offsets = (
            [0.0] if count == 1
            else [(i - (count - 1) / 2) * spread_deg for i in range(count)]
        )

        for offset in offsets:
            angle_rad = math.radians(base_angle + offset)
            dir_vec = pygame.Vector2(math.cos(angle_rad), math.sin(angle_rad))
            self._projectiles.append(Projectile(origin, dir_vec, kind, owner))

        try:
            from settings import SOUND_POWER_READY
            self._audio.play_sfx(SOUND_POWER_READY, volume=0.35, max_instances=6)
        except Exception:
            pass

        return True

    def update(self, dt: float, game) -> None:
        """Update all projectiles and resolve collisions."""
        for owner_id in list(self._shoot_cooldowns):
            remaining = max(0.0, self._shoot_cooldowns[owner_id] - dt)
            self._shoot_cooldowns[owner_id] = remaining
            owner = self._cooldown_owners.get(owner_id)
            if owner is not None:
                total = getattr(owner, "projectile_cooldown_total", 0.0)
                self._set_owner_projectile_charge(owner, remaining, total)
            if remaining == 0.0:
                del self._shoot_cooldowns[owner_id]

        disp = pygame.display.get_surface()
        w = disp.get_width() if disp else 2000
        h = disp.get_height() if disp else 2000

        for proj in self._projectiles:
            if not proj.alive:
                continue
            proj.update(dt)
            if not proj.alive:
                continue
            if (
                proj.position.x < -60 or proj.position.x > w + 60
                or proj.position.y < -60 or proj.position.y > h + 60
            ):
                proj.alive = False
                continue
            # If this projectile is a network-replicated visual-only copy,
            # skip authoritative collision resolution on clients.
            if not getattr(proj, "replica", False):
                self._check_player_collisions(proj, game)
                self._check_monster_collisions(proj, game)

        self._projectiles = [p for p in self._projectiles if p.alive]

    def _check_player_collisions(self, proj: Projectile, game) -> None:
        for player in getattr(game, "players", []):
            if player is proj.owner:
                continue
            if player in getattr(game, "eliminated_players", set()):
                continue
            if id(player) in proj._hit_players:
                continue
            if getattr(player, "has_active_shield", lambda: False)():
                continue
            hitbox = getattr(player, "get_hitbox", None)
            rect = hitbox() if callable(hitbox) else getattr(player, "rect", None)
            if rect is None:
                continue
            dist = math.hypot(proj.position.x - rect.centerx, proj.position.y - rect.centery)
            if dist > proj.radius + max(rect.width, rect.height) * 0.42:
                continue

            proj._hit_players.add(id(player))
            if not proj.pierce:
                proj.alive = False
            self._apply_hit_to_player(proj, player, game)

    def _apply_hit_to_player(self, proj: Projectile, player, game) -> None:
        if proj.velocity.length_squared() > 0:
            knock_dir = proj.velocity.normalize()
        else:
            knock_dir = pygame.Vector2(1, 0)

        push_pixels = proj.knockback * 0.05
        player.position.x += knock_dir.x * push_pixels
        player.position.y += knock_dir.y * push_pixels
        rect = getattr(player, "rect", None)
        if rect is not None:
            rect.center = (round(player.position.x), round(player.position.y))

        vel = getattr(player, "velocity", None)
        if isinstance(vel, pygame.Vector2):
            vel.x += knock_dir.x * proj.knockback * 0.22
            vel.y += knock_dir.y * proj.knockback * 0.22

        if proj.freeze_on_hit > 0 and hasattr(player, "apply_freeze"):
            player.apply_freeze(proj.freeze_on_hit)

        if hasattr(player, "take_damage") and player.take_damage(1):
            eliminate = getattr(game, "_eliminate_player", None)
            if callable(eliminate):
                eliminate(player, "hit by projectile")

    def _check_monster_collisions(self, proj: Projectile, game) -> None:
        pacman_mgr = getattr(game, "pacman_enemy_manager", None)
        if pacman_mgr is None:
            return
        for enemy in list(getattr(pacman_mgr, "enemies", [])):
            rect = getattr(enemy, "rect", None)
            if rect is None:
                continue
            dist = math.hypot(proj.position.x - rect.centerx, proj.position.y - rect.centery)
            if dist > proj.radius + max(rect.width, rect.height) * 0.60:
                continue
            if hasattr(enemy, "take_damage") and enemy.take_damage(1):
                if hasattr(enemy, "is_dying"):
                    enemy.is_dying = True
                try:
                    pacman_mgr.enemies.remove(enemy)
                except (ValueError, AttributeError):
                    pass
            proj.alive = False
            break

    def draw(self, surface: pygame.Surface) -> None:
        for proj in self._projectiles:
            proj.draw(surface)

    def apply_snapshot(self, snapshot: list) -> None:
        """Replace visual projectiles with server snapshot (client-side only).

        Snapshot is a list of dicts with keys 'x','y','vx','vy','kind','age','lifetime','owner'.
        """
        if not isinstance(snapshot, list):
            return
        visual: list[Projectile] = []
        for entry in snapshot:
            try:
                proj = Projectile.from_snapshot(entry if isinstance(entry, dict) else {})
                visual.append(proj)
            except Exception:
                continue
        # Replace client-side projectiles with visual-only set
        self._projectiles = visual

    def get_shoot_cooldown_fraction(self, owner) -> float:
        """Return 0.0 if ready to shoot, 1.0 if just fired."""
        remaining = self._shoot_cooldowns.get(id(owner), 0.0)
        if remaining <= 0:
            return 0.0
        kind = _get_kind_for_character(getattr(owner, "character_name", ""))
        total = self._effective_cooldown(_KIND_SETTINGS[kind])
        return min(1.0, remaining / total) if total > 0 else 0.0

    def reset(self) -> None:
        for owner in self._cooldown_owners.values():
            self._set_owner_projectile_charge(owner, 0.0, 0.0)
        self._projectiles.clear()
        self._shoot_cooldowns.clear()
        self._cooldown_owners.clear()


__all__ = ["Projectile", "ProjectileKind", "ProjectileManager"]
