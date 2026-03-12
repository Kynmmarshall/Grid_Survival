import math

import pygame

from assets import load_background_surface
from player import ELIMINATED, Player
from settings import (
    BACKGROUND_COLOR,
    GRID_COLS,
    GRID_ROWS,
    ISO_GRID_OFFSET_X,
    ISO_GRID_OFFSET_Y,
    ISO_TILE_DEPTH,
    ISO_TILE_H,
    ISO_TILE_W,
    TARGET_FPS,
    WINDOW_SIZE,
    WINDOW_TITLE,
)
from tile_grid import TileGrid

# HUD font size
_HUD_FONT_SIZE = 28
_HUD_COLOR     = (255, 255, 255)
_GAMEOVER_COLOR = (220, 60, 60)


class Game:
    """Main game application wrapper."""

    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = pygame.time.Clock()
        self.running = True

        self.background_surface = load_background_surface(WINDOW_SIZE)

        # ── Pre-rendered overlays ─────────────────────────────────────────
        self._shadow_surface  = self._build_shadow()
        self._vignette_surface = self._build_vignette()

        # ── Game objects ──────────────────────────────────────────────────
        self.grid   = TileGrid()
        self.player = Player(start_col=4, start_row=2)

        # ── HUD font ──────────────────────────────────────────────────────
        self.font      = pygame.font.SysFont("consolas", _HUD_FONT_SIZE, bold=True)
        self.font_big  = pygame.font.SysFont("consolas", 56, bold=True)

        self._game_over = False

    # ── Events ────────────────────────────────────────────────────────────

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

        keys = pygame.key.get_pressed()

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

        self.screen.blit(self._shadow_surface, self._shadow_rect)

        self._draw_scene()

        self.screen.blit(self._vignette_surface, (0, 0))

        self._draw_hud()

        if self._game_over:
            self._draw_game_over()

        pygame.display.flip()

    def _draw_scene(self):
        """Draw tiles and player interleaved in back-to-front isometric order."""
        # Collect and sort all tiles by depth (row + col ascending)
        all_tiles = sorted(
            (tile for row in self.grid.tiles for tile in row),
            key=lambda t: t.col + t.row,
        )

        player_depth = self.player.col + self.player.row
        player_drawn = False

        for tile in all_tiles:
            # Draw player once we pass its depth layer
            if not player_drawn and tile.col + tile.row > player_depth:
                self.player.draw(self.screen)
                player_drawn = True
            tile.draw(self.screen)

        # Player at maximum depth (or eliminated) — draw last
        if not player_drawn:
            self.player.draw(self.screen)

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

    # ── Pre-rendered overlays ─────────────────────────────────────────────

    def _build_shadow(self) -> pygame.Surface:
        """Soft elliptical shadow drawn beneath the platform."""
        hw = ISO_TILE_W // 2
        hh = ISO_TILE_H // 2
        # Grid visual centre
        cx = WINDOW_SIZE[0] // 2
        # Shadow sits just below the bottom edge of the grid
        grid_bottom = (ISO_GRID_OFFSET_Y
                       + ((GRID_COLS - 1) + (GRID_ROWS - 1)) * hh
                       + ISO_TILE_H + ISO_TILE_DEPTH)
        cy = (ISO_GRID_OFFSET_Y + grid_bottom) // 2 + ISO_TILE_DEPTH

        # Ellipse radii (wider than tall, matching isometric proportions)
        rx = int((GRID_COLS + GRID_ROWS) * hw * 0.58)
        ry = int((GRID_COLS + GRID_ROWS) * hh * 0.45)
        w, h = rx * 2, ry * 2

        # Build at quarter-res then scale up for a natural Gaussian-like blur
        qw, qh = max(w // 4, 1), max(h // 4, 1)
        small = pygame.Surface((qw, qh), pygame.SRCALPHA)
        for i in range(qw // 2):
            t = 1.0 - i / (qw / 2)
            alpha = int(70 * (t ** 1.6))
            pygame.draw.ellipse(
                small, (0, 0, 0, alpha),
                (i, int(i * qh / qw), qw - 2 * i, qh - int(2 * i * qh / qw)),
            )
        shadow = pygame.transform.smoothscale(small, (w, h))
        self._shadow_rect = shadow.get_rect(center=(cx, cy))
        return shadow

    def _build_vignette(self) -> pygame.Surface:
        """Subtle dark vignette around the screen edges."""
        w, h = WINDOW_SIZE
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = w / 2, h / 2
        max_r = math.hypot(cx, cy)
        # Draw concentric rectangles from edge inward with decreasing alpha
        steps = 80
        for i in range(steps):
            t = i / steps  # 0 = outermost, 1 = innermost
            alpha = int(100 * (1.0 - t) ** 2.2)
            if alpha < 1:
                break
            inset_x = int(t * cx * 0.9)
            inset_y = int(t * cy * 0.9)
            rect = pygame.Rect(inset_x, inset_y,
                               w - 2 * inset_x, h - 2 * inset_y)
            border_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            border_surf.fill((0, 0, 0, 0))
            # Draw only the border band by filling then cutting the inside out
            full = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            full.fill((0, 0, 0, alpha))
            # Cut inner portion
            inner_w = max(rect.w - 2 * (w // steps), 0)
            inner_h = max(rect.h - 2 * (h // steps), 0)
            if inner_w > 0 and inner_h > 0:
                inner_rect = pygame.Rect(
                    (rect.w - inner_w) // 2,
                    (rect.h - inner_h) // 2,
                    inner_w, inner_h,
                )
                full.fill((0, 0, 0, 0), inner_rect)
            surf.blit(full, rect.topleft)
        return surf

    # ── Restart ───────────────────────────────────────────────────────────

    def _restart(self):
        self.grid.reset()
        self.player.reset(start_col=4, start_row=2)
        self._game_over = False

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self):
        while self.running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()

        pygame.quit()
