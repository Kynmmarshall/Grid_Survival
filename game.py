import pygame

from ai_player import AIPlayer
from assets import load_background_surface, load_tilemap_surface
from audio import get_audio
from collision_manager import CollisionManager
from player import Player
from water import AnimatedWater
from tile_system import TMXTileManager, TileState
from hazards import HazardManager
from ui import GameHUD, EliminationScreen
from settings import (
    BACKGROUND_COLOR,
    DEBUG_DRAW_WALKABLE,
    DEBUG_VISUALS_ENABLED,
    DEBUG_WALKABLE_COLOR,
    MODE_VS_COMPUTER,
    MODE_LOCAL_MULTIPLAYER,
    TARGET_FPS,
    USE_AI_PLAYER,
    WINDOW_SIZE,
    WINDOW_TITLE,
    SOUND_PLAYER_FALL,
)


class GameManager:
    """Main game application wrapper with full feature integration."""

    def __init__(
        self,
        screen=None,
        clock=None,
        player_name: str = "Player",
        game_mode: str = MODE_VS_COMPUTER,
        selected_characters: list[str] | None = None,
    ):
        if screen is None or clock is None:
            pygame.init()
        self.screen = screen or pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = clock or pygame.time.Clock()
        self.running = True
        self.player_name = player_name
        self.game_mode = game_mode
        self.selected_characters = selected_characters or []

        # Load assets
        self.background_surface = load_background_surface(WINDOW_SIZE)
        (
            self.map_surface,
            self.tmx_data,
            self.walkable_mask,
            self.walkable_bounds,
            self.map_scale_x,
            self.map_scale_y,
            self.map_offset,
        ) = load_tilemap_surface(WINDOW_SIZE)
        self.walkable_debug_surface = None
        self.original_walkable_mask = self.walkable_mask.copy() if self.walkable_mask else None

        # Initialize game systems
        offset = self.map_offset if self.map_offset else (0, 0)
        scale_x = self.map_scale_x if self.map_scale_x else 1.0
        scale_y = self.map_scale_y if self.map_scale_y else 1.0
        self.tile_manager = TMXTileManager(
            self.tmx_data,
            scale_x,
            scale_y,
            offset,
        )
        self.collision_manager = CollisionManager()
        self.hazard_manager = HazardManager(self.collision_manager)
        self.hud = GameHUD()
        self.water = AnimatedWater()

        # Initialize players based on game mode
        self.players = []
        self.eliminated_players = []
        self.elimination_screen = None

        if self.game_mode == MODE_VS_COMPUTER:
            primary_char = self._character_choice(0)
            self.players.append(Player(character_name=primary_char))
            if USE_AI_PLAYER:
                self.players.append(AIPlayer())
        elif self.game_mode == MODE_LOCAL_MULTIPLAYER:
            player1_controls = {
                'up': pygame.K_w,
                'down': pygame.K_s,
                'left': pygame.K_a,
                'right': pygame.K_d,
                'jump': pygame.K_SPACE
            }
            player2_controls = {
                'up': pygame.K_UP,
                'down': pygame.K_DOWN,
                'left': pygame.K_LEFT,
                'right': pygame.K_RIGHT,
                'jump': pygame.K_RSHIFT
            }
            self.players.append(
                Player(controls=player1_controls, character_name=self._character_choice(0))
            )
            self.players.append(
                Player(controls=player2_controls, character_name=self._character_choice(1))
            )
        else:
            self.players.append(Player(character_name=self._character_choice(0)))

        self.hud.set_player_info(player_name, len(self.players), len(self.players))

        self.game_over = False
        self.audio = get_audio()
        self.audio.play_music()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    if self.hud.mute_rect and self.hud.mute_rect.collidepoint(event.pos):
                        self.audio.toggle_mute()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_l:
                    for player in self.players:
                        player.reset()
                elif event.key == pygame.K_r and self.game_over:
                    self._restart_game()

    def update(self, dt: float, keys):
        if keys[pygame.K_ESCAPE]:
            self.running = False
            return

        if self.game_over:
            if self.elimination_screen:
                self.elimination_screen.update(dt)
            return

        # Update game systems
        self.water.update(dt)
        self.tile_manager.update(dt)

        # Update walkable mask with disappeared/crumbling tiles
        self.walkable_mask = self.tile_manager.get_updated_walkable_mask(self.original_walkable_mask)

        self.hazard_manager.update(dt)
        self.hud.update(dt)

        # Update players
        for player in self.players[:]:
            if player in self.eliminated_players:
                continue

            was_falling_before = player.is_falling()

            if player.is_ai:
                player.update_ai(dt, self.walkable_mask, self.walkable_bounds)
            else:
                player.update(dt, keys, self.walkable_mask, self.walkable_bounds)

            # Play fall sound when player starts falling
            if not was_falling_before and player.is_falling():
                self.audio.play_sfx(SOUND_PLAYER_FALL)

            # Check water contact
            self._check_water_contact(player)

            # Check hazard collisions
            if self.hazard_manager.check_player_collision(player):
                self._eliminate_player(player, "hit by hazard")

            # Check if player fell off screen
            if player.position.y > WINDOW_SIZE[1] + 100:
                self._eliminate_player(player, "fell off")

        # Update player count in HUD
        alive_count = len(self.players) - len(self.eliminated_players)
        self.hud.set_player_info(self.player_name, alive_count, len(self.players))

        # Check game over condition
        if alive_count == 0:
            self._trigger_game_over()

    def draw(self):
        self.screen.fill(BACKGROUND_COLOR)

        # Draw background
        if self.background_surface:
            self.screen.blit(self.background_surface, (0, 0))

        # Draw water
        self.water.draw(self.screen)

        # Determine which players draw behind map
        players_behind = [p for p in self.players if p.draws_behind_map()]
        players_front = [p for p in self.players if not p.draws_behind_map()]

        # Draw players behind map
        for player in players_behind:
            player.draw(self.screen)

        # Draw TMX map with tile disappearance
        self._draw_tmx_map_with_tiles()

        # Draw warning/crumble overlays and debris particles
        self.tile_manager.draw_warning_overlays(self.screen)

        # Draw walkable debug overlay
        self._draw_walkable_debug()

        # Draw players in front of map
        for player in players_front:
            player.draw(self.screen)

        # Draw hazards
        self.hazard_manager.draw(self.screen)

        # Draw HUD
        self.hud.draw(self.screen, is_muted=self.audio.is_muted)

        # Draw elimination screen if game over
        if self.elimination_screen:
            self.elimination_screen.draw(self.screen)

        pygame.display.flip()

    def _check_water_contact(self, player):
        if not self.water.has_surface():
            return
        if player.is_drowning():
            return
        if not player.is_falling():
            return

        feet_rect = player.get_feet_rect()
        if feet_rect.bottom < self.water.surface_top():
            return

        player.start_drowning(self.water.surface_top(), player.fall_draw_behind)
        self.water.trigger_splash(player.rect.centerx)

        if player not in self.eliminated_players:
            self._eliminate_player(player, "drowned")

    def _eliminate_player(self, player, reason: str):
        """Mark a player as eliminated."""
        if player not in self.eliminated_players:
            self.eliminated_players.append(player)
            print(f"Player eliminated: {reason}")

    def _trigger_game_over(self):
        """Trigger game over state."""
        if not self.game_over:
            self.game_over = True
            self.elimination_screen = EliminationScreen(
                self.player_name,
                self.hud.survival_time,
                self.hud.score,
                "eliminated"
            )
            self.elimination_screen.show()

    def _restart_game(self):
        """Restart the game."""
        self.game_over = False
        self.elimination_screen = None
        self.eliminated_players.clear()

        self.tile_manager.reset()
        self.walkable_mask = self.original_walkable_mask.copy() if self.original_walkable_mask else None
        self.hazard_manager.reset()
        self.hud.reset()

        for player in self.players:
            player.reset()

        self.hud.set_player_info(self.player_name, len(self.players), len(self.players))

    def _draw_tmx_map_with_tiles(self):
        """Draw TMX map layers, letting missing tiles reveal the background."""
        if not self.tmx_data or not self.map_surface:
            return

        # Draw the full map surface
        self.screen.blit(self.map_surface, (0, 0))

        self.tile_manager.draw_active_tiles(self.screen)

    def _draw_walkable_debug(self):
        if not (DEBUG_VISUALS_ENABLED and DEBUG_DRAW_WALKABLE) or self.walkable_mask is None:
            return

        if self.walkable_debug_surface is None:
            color = (*DEBUG_WALKABLE_COLOR, 90)
            self.walkable_debug_surface = self.walkable_mask.to_surface(
                setcolor=color, unsetcolor=(0, 0, 0, 0)
            )

        self.screen.blit(self.walkable_debug_surface, (0, 0))

    def _character_choice(self, index: int) -> str | None:
        if not self.selected_characters:
            return None
        if 0 <= index < len(self.selected_characters):
            return self.selected_characters[index]
        return self.selected_characters[-1]

    def run(self):
        while self.running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self.handle_events()
            keys = pygame.key.get_pressed()
            self.update(dt, keys)
            self.draw()

        if hasattr(self, "audio"):
            self.audio.stop_music()
        pygame.quit()


# Backward compatibility for older imports.
Game = GameManager
