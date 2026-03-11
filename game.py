import pygame

<<<<<<< HEAD
from assets import load_background_surface
from player import ELIMINATED, Player
from settings import BACKGROUND_COLOR, TARGET_FPS, WINDOW_SIZE, WINDOW_TITLE
from tile_grid import TileGrid

# HUD font size
_HUD_FONT_SIZE = 28
_HUD_COLOR     = (255, 255, 255)
_GAMEOVER_COLOR = (220, 60, 60)
=======
from assets import load_background_surface, load_tilemap_surface
from settings import BACKGROUND_COLOR, TARGET_FPS, WINDOW_SIZE, WINDOW_TITLE
>>>>>>> 7277d45c8860066391a0d25d6144869849134703


class Game:
    """Main game application wrapper."""

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.background_surface = load_background_surface(WINDOW_SIZE)
<<<<<<< HEAD

        # ── Game objects ──────────────────────────────────────────────────
        self.grid   = TileGrid()
        self.player = Player(start_col=4, start_row=2)

        # ── HUD font ──────────────────────────────────────────────────────
        self.font      = pygame.font.SysFont("consolas", _HUD_FONT_SIZE, bold=True)
        self.font_big  = pygame.font.SysFont("consolas", 56, bold=True)

        self._game_over = False

    # ── Events ────────────────────────────────────────────────────────────
=======
        self.map_surface, self.tmx_data = load_tilemap_surface(WINDOW_SIZE)
>>>>>>> 7277d45c8860066391a0d25d6144869849134703

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

        keys = pygame.key.get_pressed()
<<<<<<< HEAD

        if keys[pygame.K_ESCAPE]:
            self.running = False

        # R to restart after game-over
        if self._game_over and keys[pygame.K_r]:
            self._restart()
            return

        if not self._game_over:
            self.player.handle_input(keys, self.grid)

    # ── Update ────────────────────────────────────────────────────────────

    def update(self, dt: float):
        if self._game_over:
            return

        self.grid.update(dt)
        self.player.update(dt, self.grid)

        if self.player.state == ELIMINATED:
            self._game_over = True

    # ── Draw ──────────────────────────────────────────────────────────────

    def draw(self):
        self.screen.fill(BACKGROUND_COLOR)

        if self.background_surface:
            self.screen.blit(self.background_surface, (0, 0))

        self.grid.draw(self.screen)
        self.player.draw(self.screen)

        self._draw_hud()

        if self._game_over:
            self._draw_game_over()

        pygame.display.flip()

    def _draw_hud(self):
        # Survival timer (top-left)
        t = int(self.player.alive_time)
        minutes, seconds = divmod(t, 60)
        timer_text = self.font.render(
            f"TIME  {minutes:02d}:{seconds:02d}", True, _HUD_COLOR
        )
        self.screen.blit(timer_text, (20, 16))

        # Remaining tiles (top-right)
        remaining = len(self.grid.normal_tiles())
        tiles_text = self.font.render(
            f"TILES  {remaining:02d}", True, _HUD_COLOR
        )
        self.screen.blit(tiles_text, (WINDOW_SIZE[0] - tiles_text.get_width() - 20, 16))

    def _draw_game_over(self):
        # Translucent overlay
        overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        # "GAME OVER"
        go_surf = self.font_big.render("GAME OVER", True, _GAMEOVER_COLOR)
        self.screen.blit(
            go_surf,
            (
                (WINDOW_SIZE[0] - go_surf.get_width())  // 2,
                (WINDOW_SIZE[1] - go_surf.get_height()) // 2 - 40,
            ),
        )

        # Survived time
        t = int(self.player.alive_time)
        minutes, seconds = divmod(t, 60)
        survived_surf = self.font.render(
            f"Survived  {minutes:02d}:{seconds:02d}", True, _HUD_COLOR
        )
        self.screen.blit(
            survived_surf,
            (
                (WINDOW_SIZE[0] - survived_surf.get_width())  // 2,
                (WINDOW_SIZE[1] - survived_surf.get_height()) // 2 + 30,
            ),
        )

        # Restart hint
        restart_surf = self.font.render("Press  R  to restart", True, (180, 180, 180))
        self.screen.blit(
            restart_surf,
            (
                (WINDOW_SIZE[0] - restart_surf.get_width())  // 2,
                (WINDOW_SIZE[1] - restart_surf.get_height()) // 2 + 80,
            ),
        )

    # ── Restart ───────────────────────────────────────────────────────────

    def _restart(self):
        self.grid.reset()
        self.player.reset(start_col=4, start_row=2)
        self._game_over = False

    # ── Main loop ─────────────────────────────────────────────────────────

=======
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

>>>>>>> 7277d45c8860066391a0d25d6144869849134703
    def run(self):
        while self.running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()

        pygame.quit()
