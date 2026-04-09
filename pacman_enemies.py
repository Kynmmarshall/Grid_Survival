from __future__ import annotations

import math
import random
from typing import Sequence

import pygame

from settings import PLAYER_SPEED


PACMAN_GHOST_SPEED = PLAYER_SPEED * 0.3
PACMAN_GHOST_KILL_RADIUS = 30
PACMAN_GHOST_ACTIVATION_DELAY = 1.25
PACMAN_GHOST_REPATH_INTERVAL = 0.14
PACMAN_GHOST_BODY_SIZE = (48, 40)
PACMAN_GHOST_SHIELD_KEEP_DISTANCE = 100.0

PACMAN_GHOST_COLORS = (
    (255, 70, 70),
    (255, 182, 255),
    (80, 255, 255),
    (255, 165, 0),
)


class PacmanEnemy:
    """Ghost-style chaser that patrols the platform and hunts live players."""

    def __init__(self, position, color, speed: float = PACMAN_GHOST_SPEED):
        self.spawn_position = pygame.Vector2(position)
        self.position = self.spawn_position.copy()
        self.speed = float(speed)
        self.color = color
        self.outline_color = (22, 22, 28)
        self.eye_color = (248, 248, 248)
        self.pupil_color = (20, 20, 20)
        self.rect = pygame.Rect(0, 0, *PACMAN_GHOST_BODY_SIZE)
        self.rect.center = (round(self.position.x), round(self.position.y))
        self._direction = pygame.Vector2(1, 0) if random.random() < 0.5 else pygame.Vector2(-1, 0)
        self._desired_direction = self._direction.copy()
        self._target_repath_timer = random.uniform(0.0, PACMAN_GHOST_REPATH_INTERVAL)
        self._activation_timer = PACMAN_GHOST_ACTIVATION_DELAY
        self._anim_time = 0.0
        self._float_phase = random.uniform(0.0, math.tau)
        self._feet_mask = None
        self._feet_mask_count = 0

    def reset(self):
        self.position = self.spawn_position.copy()
        self.rect.center = (round(self.position.x), round(self.position.y))
        self._direction = pygame.Vector2(1, 0) if random.random() < 0.5 else pygame.Vector2(-1, 0)
        self._desired_direction = self._direction.copy()
        self._target_repath_timer = random.uniform(0.0, PACMAN_GHOST_REPATH_INTERVAL)
        self._activation_timer = PACMAN_GHOST_ACTIVATION_DELAY
        self._anim_time = 0.0
        self._float_phase = random.uniform(0.0, math.tau)

    def update(
        self,
        dt: float,
        players: Sequence[object],
        walkable_mask,
        walkable_bounds,
    ) -> list[object]:
        self._anim_time += dt
        if self._activation_timer > 0:
            self._activation_timer = max(0.0, self._activation_timer - dt)
            self.rect.center = (round(self.position.x), round(self.position.y))
            return []

        target = self._find_target(players)
        if target is None:
            self.rect.center = (round(self.position.x), round(self.position.y))
            return []

        self._target_repath_timer = max(0.0, self._target_repath_timer - dt)
        if self._target_repath_timer <= 0.0 or self._desired_direction.length_squared() == 0:
            self._desired_direction = self._choose_direction(target, walkable_mask, walkable_bounds)
            self._target_repath_timer = PACMAN_GHOST_REPATH_INTERVAL * random.uniform(0.85, 1.15)

        if self._desired_direction.length_squared() == 0:
            self._desired_direction = self._fallback_direction(target)

        moved = self._move_toward(self._desired_direction, dt, walkable_mask, walkable_bounds)
        if not moved and self._direction.length_squared() > 0:
            moved = self._move_toward(self._direction, dt, walkable_mask, walkable_bounds)

        if moved and self._desired_direction.length_squared() > 0:
            self._direction = self._desired_direction.normalize()

        self.rect.center = (round(self.position.x), round(self.position.y))
        return self._collect_victims(players)

    def draw(self, surface: pygame.Surface):
        bob = math.sin(self._anim_time * 5.0 + self._float_phase) * 3.0
        draw_rect = self.rect.copy()
        draw_rect.y += int(round(bob))

        body = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
        self._draw_body(body)
        surface.blit(body, draw_rect.topleft)

    def _draw_body(self, surface: pygame.Surface) -> None:
        width, height = surface.get_size()
        body_rect = pygame.Rect(4, 4, width - 8, height - 10)
        pygame.draw.ellipse(surface, self.outline_color, body_rect)
        pygame.draw.rect(surface, self.outline_color, (4, height // 2, width - 8, height // 2 - 6))

        inner_rect = pygame.Rect(6, 6, width - 12, height - 14)
        pygame.draw.ellipse(surface, self.color, inner_rect)
        pygame.draw.rect(surface, self.color, (6, height // 2, width - 12, height // 2 - 8))

        foot_radius = max(4, width // 6)
        foot_y = height - 8
        for foot_x in (foot_radius + 2, width // 2, width - foot_radius - 2):
            pygame.draw.circle(surface, self.color, (foot_x, foot_y), foot_radius)

        eye_offset = pygame.Vector2(0, 0)
        if self._direction.length_squared() > 0:
            eye_offset = self._direction.normalize() * 2.0

        left_eye = (int(width * 0.37), int(height * 0.36))
        right_eye = (int(width * 0.63), int(height * 0.36))
        for eye_center in (left_eye, right_eye):
            pygame.draw.circle(surface, self.eye_color, eye_center, 5)
            pupil_center = (int(eye_center[0] + eye_offset.x), int(eye_center[1] + eye_offset.y))
            pygame.draw.circle(surface, self.pupil_color, pupil_center, 2)

    def _find_target(self, players: Sequence[object]):
        best_player = None
        best_distance = float("inf")
        shielded_player = None
        shielded_distance = float("inf")
        for player in players:
            if not self._is_valid_target(player):
                continue
            player_position = self._target_point(player)
            if player_position is None:
                continue
            distance = self.position.distance_to(player_position)
            if self._is_shielded(player):
                if distance < shielded_distance:
                    shielded_distance = distance
                    shielded_player = player
                continue
            if distance < best_distance:
                best_distance = distance
                best_player = player
        return best_player or shielded_player

    def _is_valid_target(self, player) -> bool:
        if getattr(player, "_eliminated", False):
            return False
        if getattr(player, "state", None) == "death":
            return False
        is_falling = getattr(player, "is_falling", None)
        if callable(is_falling) and is_falling():
            return False
        is_drowning = getattr(player, "is_drowning", None)
        if callable(is_drowning) and is_drowning():
            return False
        return True

    def _fallback_direction(self, target) -> pygame.Vector2:
        target_position = self._target_point(target) or self.position
        vector = target_position - self.position
        if vector.length_squared() == 0:
            return pygame.Vector2(0, 0)
        if self._is_shielded(target) and vector.length() <= PACMAN_GHOST_SHIELD_KEEP_DISTANCE:
            return (-vector).normalize()
        return vector.normalize()

    def _choose_direction(self, target, walkable_mask, walkable_bounds) -> pygame.Vector2:
        target_position = self._target_point(target) or self.position
        target_vector = target_position - self.position
        if target_vector.length_squared() == 0:
            return pygame.Vector2(0, 0)

        shielded = self._is_shielded(target)
        distance_to_target = target_vector.length()
        target_dir = target_vector.normalize()
        if shielded and distance_to_target <= PACMAN_GHOST_SHIELD_KEEP_DISTANCE:
            target_dir = -target_dir

        center_bias = pygame.Vector2(0, 0)
        if walkable_bounds is not None:
            center_bias = pygame.Vector2(walkable_bounds.center) - self.position
            if center_bias.length_squared() > 0:
                center_bias = center_bias.normalize()

        candidates = [
            target_dir,
            target_dir.rotate(18),
            target_dir.rotate(-18),
            target_dir.rotate(36),
            target_dir.rotate(-36),
            self._direction,
            self._direction.rotate(24),
            self._direction.rotate(-24),
            pygame.Vector2(1, 0),
            pygame.Vector2(-1, 0),
            pygame.Vector2(0, 1),
            pygame.Vector2(0, -1),
        ]

        best_direction = pygame.Vector2(0, 0)
        best_score = float("-inf")
        for candidate in candidates:
            if candidate.length_squared() == 0:
                continue
            candidate = candidate.normalize()
            probe = self.position + candidate * 32
            if not self._is_over_platform(probe, walkable_mask, walkable_bounds):
                continue

            score = candidate.dot(target_dir) * 3.5
            score += candidate.dot(self._direction) * 0.35
            if center_bias.length_squared() > 0:
                score += candidate.dot(center_bias) * 0.55
            score -= probe.distance_to(target_position) / 700.0

            if shielded:
                projected_distance = probe.distance_to(target_position)
                if projected_distance < PACMAN_GHOST_SHIELD_KEEP_DISTANCE:
                    score -= ((PACMAN_GHOST_SHIELD_KEEP_DISTANCE - projected_distance) / PACMAN_GHOST_SHIELD_KEEP_DISTANCE) * 8.0
                    score -= max(0.0, candidate.dot((target_position - self.position).normalize())) * 2.0
                else:
                    score += min(1.0, (projected_distance - PACMAN_GHOST_SHIELD_KEEP_DISTANCE) / PACMAN_GHOST_SHIELD_KEEP_DISTANCE) * 1.2

            if score > best_score:
                best_score = score
                best_direction = candidate

        if best_direction.length_squared() == 0:
            return target_dir
        return best_direction

    def _target_point(self, player) -> pygame.Vector2 | None:
        feet_getter = getattr(player, "get_feet_rect", None)
        if callable(feet_getter):
            feet_rect = feet_getter()
            if feet_rect is not None:
                return pygame.Vector2(feet_rect.center)

        position = getattr(player, "position", None)
        if position is not None:
            return pygame.Vector2(position)

        rect = getattr(player, "rect", None)
        if rect is not None:
            return pygame.Vector2(rect.center)

        return None

    def _is_shielded(self, player) -> bool:
        has_active_shield = getattr(player, "has_active_shield", None)
        if callable(has_active_shield):
            return bool(has_active_shield())
        return float(getattr(player, "_shield_timer", 0.0)) > 0.0

    def _move_toward(self, direction: pygame.Vector2, dt: float, walkable_mask, walkable_bounds) -> bool:
        if direction.length_squared() == 0:
            return False

        normalized = direction.normalize()
        for factor in (1.0, 0.75, 0.5):
            delta = normalized * self.speed * dt * factor
            if self._attempt_move(delta, walkable_mask, walkable_bounds):
                return True
        return False

    def _attempt_move(self, delta: pygame.Vector2, walkable_mask, walkable_bounds) -> bool:
        proposed = self.position + delta
        if self._is_over_platform(proposed, walkable_mask, walkable_bounds):
            self.position = proposed
            return True

        if delta.x:
            proposed_x = pygame.Vector2(self.position.x + delta.x, self.position.y)
            if self._is_over_platform(proposed_x, walkable_mask, walkable_bounds):
                self.position.x = proposed_x.x
                return True

        if delta.y:
            proposed_y = pygame.Vector2(self.position.x, self.position.y + delta.y)
            if self._is_over_platform(proposed_y, walkable_mask, walkable_bounds):
                self.position.y = proposed_y.y
                return True

        return False

    def _collect_victims(self, players: Sequence[object]) -> list[object]:
        victims: list[object] = []
        for player in players:
            if not self._can_capture(player):
                continue
            victims.append(player)
        return victims

    def _can_capture(self, player) -> bool:
        if not self._is_valid_target(player):
            return False
        if self._is_shielded(player):
            return False
        feet_getter = getattr(player, "get_feet_rect", None)
        if callable(feet_getter):
            player_rect = feet_getter()
        else:
            player_rect = getattr(player, "rect", None)
        if player_rect is None:
            return False

        enemy_rect = self.rect.inflate(-8, -8)
        return enemy_rect.colliderect(player_rect)

    def _feet_rect(self, position: pygame.Vector2) -> pygame.Rect:
        width = max(6, int(self.rect.width * 0.24))
        height = max(4, int(self.rect.height * 0.18))
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (
            round(position.x),
            round(position.y + self.rect.height * 0.24),
        )
        return rect

    def _feet_mask_for_rect(self, rect: pygame.Rect) -> pygame.mask.Mask:
        size = rect.size
        if self._feet_mask is None or self._feet_mask.get_size() != size:
            self._feet_mask = pygame.mask.Mask(size)
            self._feet_mask.fill()
            self._feet_mask_count = self._feet_mask.count()
        return self._feet_mask

    def _is_over_platform(self, position: pygame.Vector2, walkable_mask, walkable_bounds) -> bool:
        feet_rect = self._feet_rect(position)
        if walkable_bounds is not None and not walkable_bounds.colliderect(feet_rect):
            return False

        return True


class PacmanEnemyManager:
    """Container for one or more pacman-style chasers."""

    def __init__(
        self,
        spawn_positions: Sequence[tuple[int, int]],
        colors: Sequence[tuple[int, int, int]] | None = None,
        speed: float = PACMAN_GHOST_SPEED,
    ):
        palette = list(colors or PACMAN_GHOST_COLORS)
        if not palette:
            palette = [PACMAN_GHOST_COLORS[0]]

        self.enemies: list[PacmanEnemy] = []
        for index, position in enumerate(spawn_positions):
            enemy = PacmanEnemy(position, palette[index % len(palette)], speed=speed)
            enemy._activation_timer += index * 0.25
            self.enemies.append(enemy)

    def reset(self):
        for enemy in self.enemies:
            enemy.reset()

    def update(
        self,
        dt: float,
        players: Sequence[object],
        walkable_mask,
        walkable_bounds,
    ) -> list[object]:
        victims: list[object] = []
        seen_ids: set[int] = set()
        for enemy in self.enemies:
            for victim in enemy.update(dt, players, walkable_mask, walkable_bounds):
                victim_id = id(victim)
                if victim_id in seen_ids:
                    continue
                seen_ids.add(victim_id)
                victims.append(victim)
        return victims

    def snapshot_state(self) -> dict:
        """Serialize enemy state for LAN snapshot sync."""
        return {
            "enemies": [
                {
                    "x": float(enemy.position.x),
                    "y": float(enemy.position.y),
                    "dir_x": float(enemy._direction.x),
                    "dir_y": float(enemy._direction.y),
                    "activation_timer": float(enemy._activation_timer),
                    "anim_time": float(enemy._anim_time),
                }
                for enemy in self.enemies
            ]
        }

    def apply_snapshot(self, snapshot: dict | None) -> None:
        """Apply host enemy state on the LAN client."""
        if not isinstance(snapshot, dict):
            return
        states = snapshot.get("enemies")
        if not isinstance(states, list):
            return

        for enemy, state in zip(self.enemies, states):
            if not isinstance(state, dict):
                continue

            enemy.position = pygame.Vector2(
                float(state.get("x", enemy.position.x)),
                float(state.get("y", enemy.position.y)),
            )
            enemy.rect.center = (round(enemy.position.x), round(enemy.position.y))

            direction = pygame.Vector2(
                float(state.get("dir_x", enemy._direction.x)),
                float(state.get("dir_y", enemy._direction.y)),
            )
            if direction.length_squared() > 0:
                enemy._direction = direction.normalize()
                enemy._desired_direction = enemy._direction.copy()

            enemy._activation_timer = max(
                0.0,
                float(state.get("activation_timer", enemy._activation_timer)),
            )
            enemy._anim_time = float(state.get("anim_time", enemy._anim_time))

    def draw(self, surface: pygame.Surface):
        for enemy in sorted(self.enemies, key=lambda enemy: enemy.position.y):
            enemy.draw(surface)


__all__ = ["PacmanEnemy", "PacmanEnemyManager"]