import pygame

from ai_player import AIPlayer
from assets import load_background_surface, load_tilemap_surface
from player import Player
from water import AnimatedWater
from settings import (
    BACKGROUND_COLOR,
    DEBUG_DRAW_WALKABLE,
    DEBUG_VISUALS_ENABLED,
    DEBUG_WALKABLE_COLOR,
    TARGET_FPS,
    USE_AI_PLAYER,
    WINDOW_SIZE,
    WINDOW_TITLE,
)


class Game:
    """Main game application wrapper."""

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.background_surface = load_background_surface(WINDOW_SIZE)
        (
            self.map_surface,
            self.tmx_data,
            self.walkable_mask,
            self.walkable_bounds,
        ) = load_tilemap_surface(WINDOW_SIZE)
        self.walkable_debug_surface = None
        self.player = AIPlayer() if USE_AI_PLAYER else Player()
        self.water = AnimatedWater()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_l:
                    self.player.reset()

    def update(self, dt: float, keys):
        if keys[pygame.K_ESCAPE]:
            self.running = False
            return

        self.water.update(dt)
        if self.player.is_ai:
            self.player.update_ai(dt, self.walkable_mask, self.walkable_bounds)
        else:
            self.player.update(dt, keys, self.walkable_mask, self.walkable_bounds)
        self._check_water_contact()

    def draw(self):
        self.screen.fill(BACKGROUND_COLOR)

        if self.background_surface:
            self.screen.blit(self.background_surface, (0, 0))
        self.water.draw(self.screen)
        draw_player_first = self.player.draws_behind_map()

        if draw_player_first:
            self.player.draw(self.screen)

        if self.map_surface:
            self.screen.blit(self.map_surface, (0, 0))

        self._draw_walkable_debug()

        if not draw_player_first:
            self.player.draw(self.screen)

        pygame.display.flip()

    def _check_water_contact(self):
        if not self.water.has_surface():
            return
        if self.player.is_drowning():
            return
        if not self.player.is_falling():
            return

        feet_rect = self.player.get_feet_rect()
        if feet_rect.bottom < self.water.surface_top():
            return

        self.player.start_drowning(self.water.surface_top(), self.player.fall_draw_behind)
        self.water.trigger_splash(self.player.rect.centerx)

    def _draw_walkable_debug(self):
        if not (DEBUG_VISUALS_ENABLED and DEBUG_DRAW_WALKABLE) or self.walkable_mask is None:
            return

        if self.walkable_debug_surface is None:
            color = (*DEBUG_WALKABLE_COLOR, 90)
            self.walkable_debug_surface = self.walkable_mask.to_surface(
                setcolor=color, unsetcolor=(0, 0, 0, 0)
            )

        self.screen.blit(self.walkable_debug_surface, (0, 0))

    def run(self):
        while self.running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self.handle_events()
            keys = pygame.key.get_pressed()
            self.update(dt, keys)
            self.draw()

        pygame.quit()
