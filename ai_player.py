"""Adaptive AI player with difficulty tiers and hazard awareness."""

import random
from typing import Dict

import pygame

from player import Player
from settings import AI_DEFAULT_DIFFICULTY, PLAYER_START_POS


DIFFICULTY_PRESETS: Dict[int, dict] = {
    1: {
        "decision_interval": 0.9,
        "ray_distance": 110,
        "ray_step": 18,
        "edge_bias": 0.35,
        "panic_threshold": 0.75,
        "panic_force": 0.55,
        "smoothing": 2.5,
        "center_bias": 0.15,
        "momentum_bonus": 0.2,
        "idle_penalty": 0.4,
        "explore_jitter": 0.8,
    },
    2: {
        "decision_interval": 0.65,
        "ray_distance": 140,
        "ray_step": 14,
        "edge_bias": 0.55,
        "panic_threshold": 0.6,
        "panic_force": 0.65,
        "smoothing": 3.4,
        "center_bias": 0.25,
        "momentum_bonus": 0.35,
        "idle_penalty": 0.35,
        "explore_jitter": 0.65,
    },
    3: {
        "decision_interval": 0.45,
        "ray_distance": 175,
        "ray_step": 12,
        "edge_bias": 0.75,
        "panic_threshold": 0.45,
        "panic_force": 0.8,
        "smoothing": 4.6,
        "center_bias": 0.35,
        "momentum_bonus": 0.45,
        "idle_penalty": 0.3,
        "explore_jitter": 0.5,
    },
    4: {
        "decision_interval": 0.3,
        "ray_distance": 210,
        "ray_step": 10,
        "edge_bias": 0.95,
        "panic_threshold": 0.35,
        "panic_force": 0.95,
        "smoothing": 5.9,
        "center_bias": 0.45,
        "momentum_bonus": 0.55,
        "idle_penalty": 0.2,
        "explore_jitter": 0.35,
    },
    5: {
        "decision_interval": 0.18,
        "ray_distance": 240,
        "ray_step": 8,
        "edge_bias": 1.1,
        "panic_threshold": 0.25,
        "panic_force": 1.1,
        "smoothing": 7.2,
        "center_bias": 0.55,
        "momentum_bonus": 0.65,
        "idle_penalty": 0.1,
        "explore_jitter": 0.2,
    },
}

CANDIDATE_DIRECTIONS = (
    pygame.Vector2(0, 0),
    pygame.Vector2(1, 0),
    pygame.Vector2(-1, 0),
    pygame.Vector2(0, 1),
    pygame.Vector2(0, -1),
    pygame.Vector2(1, 1).normalize(),
    pygame.Vector2(-1, 1).normalize(),
    pygame.Vector2(1, -1).normalize(),
    pygame.Vector2(-1, -1).normalize(),
)

EDGE_SAMPLE_OFFSETS = (
    pygame.Vector2(0, 28),
    pygame.Vector2(0, -28),
    pygame.Vector2(28, 0),
    pygame.Vector2(-28, 0),
    pygame.Vector2(22, 22),
    pygame.Vector2(-22, 22),
    pygame.Vector2(22, -22),
    pygame.Vector2(-22, -22),
)


def _clamp_difficulty(value: int) -> int:
    return max(1, min(5, int(value)))


class AIPlayer(Player):
    """Versatile AI opponent whose awareness scales with difficulty."""

    def __init__(self, position=None, difficulty: int = AI_DEFAULT_DIFFICULTY):
        super().__init__(position=position or PLAYER_START_POS)
        self.is_ai = True
        self.difficulty = _clamp_difficulty(difficulty)
        self.config = DIFFICULTY_PRESETS[self.difficulty]
        self._rng = random.Random()
        self._decision_timer = 0.0
        self._current_direction = pygame.Vector2(0, 0)
        self._desired_direction = pygame.Vector2(0, 0)
        self._last_escape_vector = pygame.Vector2(0, 0)

    def reset(self):
        super().reset()
        self._decision_timer = 0.0
        self._current_direction.update(0, 0)
        self._desired_direction.update(0, 0)
        self._last_escape_vector.update(0, 0)

    def update_ai(self, dt: float, walkable_mask, walkable_bounds, hazard_manager=None, pacman_enemy_manager=None):
        self._tick_status_effects(dt)
        if self.is_frozen():
            self._current_direction.update(0, 0)
            self._desired_direction.update(0, 0)
            self._update_with_move_vector(
                dt,
                pygame.Vector2(0, 0),
                walkable_mask,
                walkable_bounds,
                jump_pressed=False,
            )
            return

        if self.power and hasattr(self.power, "blocks_player_motion") and self.power.blocks_player_motion():
            self._current_direction.update(0, 0)
            self._desired_direction.update(0, 0)
            self.velocity.update(0, 0)
            self.rect.center = (round(self.position.x), round(self.position.y))
            return

        self._decision_timer += dt

        emergency = self._emergency_vector(
            walkable_mask,
            walkable_bounds,
            hazard_manager,
            pacman_enemy_manager,
        )
        if emergency is not None:
            self._desired_direction = emergency
            self._decision_timer = 0.0
        elif self._decision_timer >= self.config["decision_interval"]:
            self._decision_timer = 0.0
            self._desired_direction = self._choose_direction(
                walkable_mask,
                walkable_bounds,
                hazard_manager,
                pacman_enemy_manager,
            )

        blend_rate = min(1.0, dt * self.config["smoothing"])
        self._current_direction = self._current_direction.lerp(self._desired_direction, blend_rate)

        if self._current_direction.length_squared() > 1e-3:
            move_dir = self._current_direction.normalize()
        else:
            move_dir = pygame.Vector2(0, 0)

        self._update_with_move_vector(
            dt,
            move_dir,
            walkable_mask,
            walkable_bounds,
            jump_pressed=False,
        )

    def _emergency_vector(self, walkable_mask, walkable_bounds, hazard_manager=None, pacman_enemy_manager=None):
        edge_danger = self._edge_danger_level(walkable_mask) if walkable_mask else 0.0
        threat_escape, threat_pressure = self._threat_escape_vector(hazard_manager, pacman_enemy_manager)
        if edge_danger < self.config["panic_threshold"] and threat_pressure <= 0.0:
            return None

        escape = pygame.Vector2(0, 0)
        if threat_escape is not None:
            escape += threat_escape

        if edge_danger >= self.config["panic_threshold"]:
            safe_vector = self._vector_toward_safe_zone(walkable_bounds)
            if safe_vector.length_squared() == 0:
                safe_vector = pygame.Vector2(self._rng.uniform(-1, 1), self._rng.uniform(-1, 1))
            if safe_vector.length_squared() > 0:
                escape += safe_vector.normalize() * (0.5 + edge_danger)

        if escape.length_squared() == 0:
            safe_vector = pygame.Vector2(self._rng.uniform(-1, 1), self._rng.uniform(-1, 1))
            escape = safe_vector

        if escape.length_squared() == 0:
            return None

        escape = escape.normalize()
        self._last_escape_vector = escape * self.config["panic_force"]
        return escape

    def _choose_direction(self, walkable_mask, walkable_bounds, hazard_manager=None, pacman_enemy_manager=None) -> pygame.Vector2:
        best_dir = pygame.Vector2(0, 0)
        best_score = float("-inf")
        for direction in CANDIDATE_DIRECTIONS:
            score = self._score_direction(
                direction,
                walkable_mask,
                walkable_bounds,
                hazard_manager,
                pacman_enemy_manager,
            )
            if score > best_score:
                best_score = score
                best_dir = direction
        return best_dir

    def _score_direction(self, direction: pygame.Vector2, walkable_mask, walkable_bounds, hazard_manager=None, pacman_enemy_manager=None) -> float:
        if direction.length_squared() == 0:
            idle_penalty = self.config["idle_penalty"]
            jitter = self._rng.uniform(-self.config["explore_jitter"], self.config["explore_jitter"])
            return -idle_penalty + jitter

        direction = direction.normalize()
        distance = self._walkable_distance(direction, walkable_mask)
        distance_score = distance / self.config["ray_distance"]

        center_score = self._center_bias_score(direction, walkable_bounds)
        edge_score = self._edge_margin_score(direction, walkable_bounds)
        momentum = max(0.0, direction.dot(self._current_direction)) * self.config["momentum_bonus"]
        escape_bias = direction.dot(self._last_escape_vector)
        jitter = self._rng.uniform(-self.config["explore_jitter"], self.config["explore_jitter"])
        threat_score = self._threat_safety_score(probe=self.position + direction * 40, hazard_manager=hazard_manager, pacman_enemy_manager=pacman_enemy_manager)

        return distance_score + edge_score + center_score + momentum + escape_bias + threat_score + jitter

    def _walkable_distance(self, direction: pygame.Vector2, walkable_mask) -> float:
        if not walkable_mask:
            return self.config["ray_distance"]
        step = self.config["ray_step"]
        max_distance = self.config["ray_distance"]
        sampled = 0.0
        probe = pygame.Vector2(self.position)
        while sampled < max_distance:
            probe += direction * step
            sampled += step
            if not self._is_over_platform(probe, walkable_mask):
                break
        return min(sampled, max_distance)

    def _edge_margin_score(self, direction: pygame.Vector2, walkable_bounds) -> float:
        if walkable_bounds is None:
            return 0.0
        probe = self.position + direction * 40
        feet = self._feet_rect(probe)
        margins = (
            feet.left - walkable_bounds.left,
            walkable_bounds.right - feet.right,
            feet.top - walkable_bounds.top,
            walkable_bounds.bottom - feet.bottom,
        )
        min_margin = max(0.0, min(margins))
        max_dimension = max(walkable_bounds.width, walkable_bounds.height)
        normalized = min_margin / max_dimension if max_dimension else 0.0
        return normalized * self.config["edge_bias"]

    def _center_bias_score(self, direction: pygame.Vector2, walkable_bounds) -> float:
        if walkable_bounds is None:
            return 0.0
        center = pygame.Vector2(walkable_bounds.center)
        to_center = (center - self.position)
        if to_center.length_squared() == 0:
            return 0.0
        to_center = to_center.normalize()
        alignment = max(0.0, direction.dot(to_center))
        return alignment * self.config["center_bias"]

    def _edge_danger_level(self, walkable_mask) -> float:
        if not walkable_mask:
            return 0.0
        danger_hits = 0
        for offset in EDGE_SAMPLE_OFFSETS:
            sample_point = self.position + offset
            if not self._is_over_platform(sample_point, walkable_mask):
                danger_hits += 1
        return danger_hits / len(EDGE_SAMPLE_OFFSETS)

    def _vector_toward_safe_zone(self, walkable_bounds) -> pygame.Vector2:
        if walkable_bounds:
            center = pygame.Vector2(walkable_bounds.center)
            return center - self.position
        return pygame.Vector2(-self._current_direction.y, self._current_direction.x)

    def _threat_escape_vector(self, hazard_manager=None, pacman_enemy_manager=None):
        escape = pygame.Vector2(0, 0)
        pressure = 0.0

        if hazard_manager:
            for bullet in getattr(hazard_manager, "bullets", []):
                if not getattr(bullet, "active", False):
                    continue
                bullet_pos = pygame.Vector2(getattr(bullet, "position", self.position))
                vector = self.position - bullet_pos
                distance = vector.length()
                if distance <= 220 and distance > 0:
                    influence = max(0.0, 1.0 - (distance / 220.0))
                    escape += vector.normalize() * influence * 1.1
                    pressure = max(pressure, influence)

            for trap in getattr(hazard_manager, "traps", []):
                trap_pos = pygame.Vector2(getattr(trap, "position", self.position))
                vector = self.position - trap_pos
                distance = vector.length()
                if distance <= 260 and distance > 0:
                    influence = max(0.0, 1.0 - (distance / 260.0))
                    escape += vector.normalize() * influence * 0.9
                    pressure = max(pressure, influence)

        if pacman_enemy_manager:
            for enemy in getattr(pacman_enemy_manager, "enemies", []):
                if getattr(enemy, "_activation_timer", 0.0) > 0:
                    continue
                enemy_pos = pygame.Vector2(getattr(enemy, "position", self.position))
                vector = self.position - enemy_pos
                distance = vector.length()
                if distance <= 320 and distance > 0:
                    influence = max(0.0, 1.0 - (distance / 320.0))
                    escape += vector.normalize() * influence * 1.6
                    pressure = max(pressure, influence)

        if escape.length_squared() == 0:
            return None, pressure
        return escape, pressure

    def _threat_safety_score(self, probe: pygame.Vector2, hazard_manager=None, pacman_enemy_manager=None) -> float:
        score = 0.0

        if hazard_manager:
            is_safe = getattr(hazard_manager, "is_position_safe", None)
            if callable(is_safe) and not is_safe((probe.x, probe.y), radius=28):
                score -= 4.0 + (0.25 * self.difficulty)
            else:
                nearest_hazard = None
                for bullet in getattr(hazard_manager, "bullets", []):
                    if not getattr(bullet, "active", False):
                        continue
                    bullet_pos = pygame.Vector2(getattr(bullet, "position", probe))
                    distance = probe.distance_to(bullet_pos)
                    nearest_hazard = distance if nearest_hazard is None else min(nearest_hazard, distance)
                for trap in getattr(hazard_manager, "traps", []):
                    trap_pos = pygame.Vector2(getattr(trap, "position", probe))
                    distance = probe.distance_to(trap_pos)
                    nearest_hazard = distance if nearest_hazard is None else min(nearest_hazard, distance)

                if nearest_hazard is not None:
                    safe_distance = 180.0 + 12.0 * self.difficulty
                    score += min(1.0, nearest_hazard / safe_distance) * (1.0 + 0.12 * self.difficulty)

        if pacman_enemy_manager:
            nearest_enemy = None
            for enemy in getattr(pacman_enemy_manager, "enemies", []):
                if getattr(enemy, "_activation_timer", 0.0) > 0:
                    continue
                enemy_pos = pygame.Vector2(getattr(enemy, "position", probe))
                distance = probe.distance_to(enemy_pos)
                nearest_enemy = distance if nearest_enemy is None else min(nearest_enemy, distance)

            if nearest_enemy is not None:
                safe_distance = 240.0 + 18.0 * self.difficulty
                score += min(1.0, nearest_enemy / safe_distance) * (1.1 + 0.14 * self.difficulty)

        return score