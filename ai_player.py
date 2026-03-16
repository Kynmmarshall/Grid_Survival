"""Basic AI controller for the animated map-based player."""

import random

import pygame

from player import Player
from settings import (
    AI_DECISION_INTERVAL,
    AI_EDGE_MARGIN_WEIGHT,
    AI_LOOKAHEAD_DISTANCE,
    PLAYER_START_POS,
)


class AIPlayer(Player):
    """Simple rule-based AI that wanders safely on the walkable surface."""

    def __init__(self, position=None):
        super().__init__(position=position or PLAYER_START_POS)
        self.is_ai = True
        self._rng = random.Random()
        self._decision_timer = 0.0
        self._current_direction = pygame.Vector2(0, 0)

    def reset(self):
        super().reset()
        self._decision_timer = 0.0
        self._current_direction.update(0, 0)

    def update_ai(self, dt: float, walkable_mask, walkable_bounds):
        self._decision_timer += dt

        needs_new_direction = self._decision_timer >= AI_DECISION_INTERVAL
        if self._current_direction.length_squared() > 0:
            probe = self.position + self._current_direction * AI_LOOKAHEAD_DISTANCE
            if not self._is_over_platform(probe, walkable_mask):
                needs_new_direction = True

        if needs_new_direction:
            self._decision_timer = 0.0
            self._current_direction = self._choose_direction(walkable_mask, walkable_bounds)

        self._update_with_move_vector(
            dt,
            self._current_direction,
            walkable_mask,
            walkable_bounds,
        )

    def _choose_direction(self, walkable_mask, walkable_bounds) -> pygame.Vector2:
        candidates = [
            pygame.Vector2(0, 0),
            pygame.Vector2(1, 0),
            pygame.Vector2(-1, 0),
            pygame.Vector2(0, 1),
            pygame.Vector2(0, -1),
        ]

        scored = []
        for direction in candidates:
            score = self._score_direction(direction, walkable_mask, walkable_bounds)
            scored.append((score, direction))

        scored.sort(key=lambda item: item[0], reverse=True)
        best_score = scored[0][0]
        best = [direction for score, direction in scored if score == best_score]
        return self._rng.choice(best)

    def _score_direction(self, direction: pygame.Vector2, walkable_mask, walkable_bounds) -> int:
        probe = self.position
        if direction.length_squared() > 0:
            probe = self.position + direction.normalize() * AI_LOOKAHEAD_DISTANCE

        if not self._is_over_platform(probe, walkable_mask):
            return -10000

        score = 100

        if direction.length_squared() > 0:
            further_probe = probe + direction.normalize() * AI_LOOKAHEAD_DISTANCE
            if self._is_over_platform(further_probe, walkable_mask):
                score += 35

        if walkable_bounds is not None:
            feet = self._feet_rect(probe)
            margin = min(
                feet.left - walkable_bounds.left,
                walkable_bounds.right - feet.right,
                feet.top - walkable_bounds.top,
                walkable_bounds.bottom - feet.bottom,
            )
            score += int(margin * AI_EDGE_MARGIN_WEIGHT)

        if direction.length_squared() == 0:
            score -= 8

        if direction == self._current_direction:
            score += 6

        score += self._rng.randint(0, 3)
        return score
