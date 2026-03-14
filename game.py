import math

import pygame

from assets import load_background_surface
from hazards import HazardManager
from player import ELIMINATED, KEYS_ARROWS, KEYS_WASD, Player
from settings import (
    BACKGROUND_COLOR,
    DIFFICULTY_INTERVAL,
    DIFFICULTY_MIN_INTERVAL,
    DIFFICULTY_SPEED_FACTOR,
    GRID_COLS,
    GRID_ROWS,
    ISO_GRID_OFFSET_X,
    ISO_GRID_OFFSET_Y,
    ISO_TILE_DEPTH,
    ISO_TILE_H,
    ISO_TILE_W,
    PLAYER_COLOR,
    PLAYER_COLOR_2,
    TARGET_FPS,
    TILES_PER_SECOND,
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
        # Bake vignette directly into the background so it costs nothing per frame
        self._bake_vignette_into_background()

        # ── Game objects ──────────────────────────────────────────────────
        self.grid    = TileGrid()
        self.players = [
            Player(start_col=3, start_row=2, keys=KEYS_ARROWS,
                   color=PLAYER_COLOR, player_id=1),
            Player(start_col=6, start_row=3, keys=KEYS_WASD,
                   color=PLAYER_COLOR_2, player_id=2),
        ]
        self.hazards = HazardManager(self.grid)

        # ── Difficulty ────────────────────────────────────────────────────
        self._difficulty_timer: float = 0.0
        self._current_spawn_interval: float = 1.0 / TILES_PER_SECOND

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
            for player in self.players:
                player.handle_input(keys, self.grid)

    # ── Update ────────────────────────────────────────────────────────────

    def update(self, dt: float):
        if self._game_over:
            return

        self.grid.update(dt)
        for player in self.players:
            player.update(dt, self.grid)
        self.hazards.update(dt, self.players)

        # Difficulty scaling
        self._difficulty_timer += dt
        if self._difficulty_timer >= DIFFICULTY_INTERVAL:
            self._difficulty_timer -= DIFFICULTY_INTERVAL
            self._current_spawn_interval = max(
                DIFFICULTY_MIN_INTERVAL,
                self._current_spawn_interval * DIFFICULTY_SPEED_FACTOR,
            )
            self.grid.set_spawn_interval(self._current_spawn_interval)

        if all(p.state == ELIMINATED for p in self.players):
            self._game_over = True

    # ── Draw ──────────────────────────────────────────────────────────────

    def draw(self):
        self.screen.fill(BACKGROUND_COLOR)

        if self.background_surface:
            self.screen.blit(self.background_surface, (0, 0))

        self.screen.blit(self._shadow_surface, self._shadow_rect)

        self._draw_scene()
        self.hazards.draw(self.screen)

        self._draw_hud()

        if self._game_over:
            self._draw_game_over()

        pygame.display.flip()

    def _draw_scene(self):
        """Draw tiles and players interleaved in back-to-front isometric order."""
        all_tiles = sorted(
            (tile for row in self.grid.tiles for tile in row),
            key=lambda t: t.col + t.row,
        )

        # Build list of (depth, drawable) for players too
        drawables: list[tuple[int, object]] = []
        for tile in all_tiles:
            drawables.append((tile.col + tile.row, tile))
        for player in self.players:
            if player.state != ELIMINATED:
                drawables.append((player.col + player.row, player))

        # Stable sort: tiles before players at the same depth
        drawables.sort(key=lambda d: d[0])

        for _, obj in drawables:
            obj.draw(self.screen)

    def _draw_hud(self):
        # Best survival timer (top-left) — longest alive among all players
        best_time = max(p.alive_time for p in self.players)
        t = int(best_time)
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

        # Per-player status (bottom)
        for i, player in enumerate(self.players):
            label = f"P{player.player_id}"
            if player.state == ELIMINATED:
                pt = int(player.alive_time)
                pm, ps = divmod(pt, 60)
                text = f"{label}  ELIMINATED  {pm:02d}:{ps:02d}"
                color = (180, 60, 60)
            else:
                pt = int(player.alive_time)
                pm, ps = divmod(pt, 60)
                text = f"{label}  {pm:02d}:{ps:02d}"
                color = player.color
            surf = self.font.render(text, True, color)
            x = 20 + i * (WINDOW_SIZE[0] // 2)
            self.screen.blit(surf, (x, WINDOW_SIZE[1] - 40))

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

        # Survived time — show best
        best_time = max(p.alive_time for p in self.players)
        t = int(best_time)
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
        """Soft elliptical shadow drawn beneath the platform (numpy)."""
        import numpy as np

        hw = ISO_TILE_W // 2
        hh = ISO_TILE_H // 2

        # Ellipse radii — wide & shallow, matching the isometric footprint
        rx = int((GRID_COLS + GRID_ROWS) * hw * 0.55)
        ry = int((GRID_COLS + GRID_ROWS) * hh * 0.38)
        w, h = rx * 2, ry * 2

        # Per-pixel elliptical distance → alpha
        ys = np.linspace(-1, 1, h).reshape(-1, 1)
        xs = np.linspace(-1, 1, w).reshape(1, -1)
        dist = np.sqrt(xs ** 2 + ys ** 2)            # 0 at centre, 1 at edge
        alpha = np.clip(1.0 - dist, 0, 1) ** 1.8     # smooth falloff
        alpha = (alpha * 50).astype(np.uint8)         # max 50 — subtle

        pixels = np.zeros((h, w, 4), dtype=np.uint8)
        pixels[:, :, 3] = alpha                       # black with varying alpha

        shadow = pygame.image.frombuffer(pixels.tobytes(), (w, h), "RGBA").convert_alpha()

        # Position: centred horizontally, vertically at grid's visual centre + depth offset
        grid_bottom = (ISO_GRID_OFFSET_Y
                       + ((GRID_COLS - 1) + (GRID_ROWS - 1)) * hh
                       + ISO_TILE_H + ISO_TILE_DEPTH)
        cx = WINDOW_SIZE[0] // 2
        cy = (ISO_GRID_OFFSET_Y + grid_bottom) // 2 + ISO_TILE_DEPTH
        self._shadow_rect = shadow.get_rect(center=(cx, cy))
        return shadow

    def _build_vignette(self) -> pygame.Surface:
        """Smooth radial vignette — dark at edges, transparent in centre (numpy)."""
        import numpy as np

        w, h = WINDOW_SIZE
        ys = np.linspace(-1, 1, h).reshape(-1, 1)
        xs = np.linspace(-1, 1, w).reshape(1, -1)
        dist = np.sqrt(xs ** 2 + ys ** 2) / math.sqrt(2)
        alpha = np.clip((dist - 0.4) / 0.6, 0, 1) ** 1.8
        alpha = (alpha * 120).astype(np.uint8)

        pixels = np.zeros((h, w, 4), dtype=np.uint8)
        pixels[:, :, 3] = alpha

        return pygame.image.frombuffer(pixels.tobytes(), (w, h), "RGBA").convert_alpha()

    def _bake_vignette_into_background(self) -> None:
        """Composite the vignette onto the background surface once."""
        vignette = self._build_vignette()
        if self.background_surface is None:
            self.background_surface = pygame.Surface(WINDOW_SIZE).convert()
            self.background_surface.fill(BACKGROUND_COLOR)
        self.background_surface.blit(vignette, (0, 0))

    # ── Restart ───────────────────────────────────────────────────────────

    def _restart(self):
        self.grid.reset()
        self.players[0].reset(start_col=3, start_row=2)
        self.players[1].reset(start_col=6, start_row=3)
        self.hazards.reset()
        self._difficulty_timer = 0.0
        self._current_spawn_interval = 1.0 / TILES_PER_SECOND
        self.grid.set_spawn_interval(self._current_spawn_interval)
        self._game_over = False

    # ── Main loop ─────────────────────────────────────────────────────────

    def run(self):
        while self.running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()

        pygame.quit()
