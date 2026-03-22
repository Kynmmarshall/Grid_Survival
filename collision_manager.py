"""Collision helpers for pixel-perfect interactions."""

from __future__ import annotations

from typing import Dict, Tuple

import pygame


class CollisionManager:
    """Caches masks and performs overlap checks between game entities."""

    def __init__(self):
        self._player_masks: Dict[int, pygame.mask.Mask] = {}
        self._bullet_masks: Dict[int, pygame.mask.Mask] = {}

    # ---------------------------------------------------------------------
    # Mask helpers
    # ---------------------------------------------------------------------

    def _player_mask(self, player) -> pygame.mask.Mask:
        surface = player.current_animation.image
        key = id(surface)
        mask = self._player_masks.get(key)
        if mask is None:
            mask = pygame.mask.from_surface(surface)
            self._player_masks[key] = mask
        return mask

    def _circle_mask(self, radius: int) -> pygame.mask.Mask:
        radius = max(1, int(radius))
        mask = self._bullet_masks.get(radius)
        if mask is None:
            diameter = radius * 2
            surface = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
            pygame.draw.circle(surface, (255, 255, 255), (radius, radius), radius)
            mask = pygame.mask.from_surface(surface)
            self._bullet_masks[radius] = mask
        return mask

    # ---------------------------------------------------------------------
    # Collision routines
    # ---------------------------------------------------------------------

    def bullet_hits_player(self, bullet, player) -> bool:
        if not bullet.active:
            return False
        player_mask = self._player_mask(player)
        bullet_mask = self._circle_mask(bullet.radius)
        bullet_rect = bullet.get_rect()
        offset = (
            bullet_rect.left - player.rect.left,
            bullet_rect.top - player.rect.top,
        )
        hit = player_mask.overlap(bullet_mask, offset) is not None
        if hit:
            bullet.active = False
        return hit

    def reset_caches(self):
        self._player_masks.clear()
        self._bullet_masks.clear()
