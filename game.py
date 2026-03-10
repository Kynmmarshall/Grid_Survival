import pygame

from assets import load_background_surface, load_tilemap_surface
from settings import BACKGROUND_COLOR, TARGET_FPS, WINDOW_SIZE, WINDOW_TITLE


class Game:
    """Main game application wrapper."""

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.background_surface = load_background_surface(WINDOW_SIZE)
        self.map_surface, self.tmx_data = load_tilemap_surface(WINDOW_SIZE)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

        keys = pygame.key.get_pressed()
        if keys[pygame.K_ESCAPE]:
            self.running = False

    def update(self, dt: float):
        """Advance game state. Placeholder for future logic."""
        _ = dt  # suppress unused variable warnings for now

    def draw(self):
        self.screen.fill(BACKGROUND_COLOR)
        if self.background_surface:
            self.screen.blit(self.background_surface, (0, 0))
        if self.map_surface:
            self.screen.blit(self.map_surface, (0, 0))
        pygame.display.flip()

    def run(self):
        while self.running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()

        pygame.quit()
