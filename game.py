import pygame

from ai_player import AIPlayer
from assets import load_background_surface, load_tilemap_surface
from player import Player
from water import AnimatedWater
from tile_system import TileGrid
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
)


class GameManager:
    """Main game application wrapper with full feature integration."""

    def __init__(self, screen=None, clock=None, player_name: str = "Player", game_mode: str = MODE_VS_COMPUTER):
        if screen is None or clock is None:
            pygame.init()
        self.screen = screen or pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = clock or pygame.time.Clock()
        self.running = True
        self.player_name = player_name
        self.game_mode = game_mode

        # Load assets
        self.background_surface = load_background_surface(WINDOW_SIZE)
        (
            self.map_surface,
            self.tmx_data,
            self.walkable_mask,
            self.walkable_bounds,
        ) = load_tilemap_surface(WINDOW_SIZE)
        self.walkable_debug_surface = None

        # Initialize game systems
        self.tile_grid = TileGrid()
        self.hazard_manager = HazardManager()
        self.hud = GameHUD()
        self.water = AnimatedWater()
        
        # Initialize players based on game mode
        self.players = []
        self.eliminated_players = []
        self.elimination_screen = None
        
        if self.game_mode == MODE_VS_COMPUTER:
            # Single player vs AI
            use_ai = USE_AI_PLAYER
            self.players.append(AIPlayer() if use_ai else Player())
            self.hud.set_player_info(player_name, 1, 1)
        elif self.game_mode == MODE_LOCAL_MULTIPLAYER:
            # Local multiplayer with different controls
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
            self.players.append(Player(controls=player1_controls))
            self.players.append(Player(controls=player2_controls))
            self.hud.set_player_info(player_name, 2, 2)
        else:
            # Default single player
            self.players.append(Player())
            self.hud.set_player_info(player_name, 1, 1)
        
        self.game_over = False

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_l:
                    # Reset all players
                    for player in self.players:
                        player.reset()
                elif event.key == pygame.K_r and self.game_over:
                    # Restart game
                    self._restart_game()

    def update(self, dt: float, keys):
        if keys[pygame.K_ESCAPE]:
            self.running = False
            return
        
        # Don't update game if game over
        if self.game_over:
            if self.elimination_screen:
                self.elimination_screen.update(dt)
            return

        # Update game systems
        self.water.update(dt)
        self.tile_grid.update(dt)
        self.hazard_manager.update(dt)
        self.hud.update(dt)
        
        # Update players
        for player in self.players[:]:
            if player in self.eliminated_players:
                continue
            
            if player.is_ai:
                player.update_ai(dt, self.walkable_mask, self.walkable_bounds)
            else:
                player.update(dt, keys, self.walkable_mask, self.walkable_bounds)
            
            # Check water contact
            self._check_water_contact(player)
            
            # Check hazard collisions
            if self.hazard_manager.check_player_collision(player.rect):
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
        
        # Draw tile grid
        self.tile_grid.draw(self.screen)
        
        # Determine which players draw behind map
        players_behind = [p for p in self.players if p.draws_behind_map()]
        players_front = [p for p in self.players if not p.draws_behind_map()]
        
        # Draw players behind map
        for player in players_behind:
            player.draw(self.screen)

        # Draw TMX map
        if self.map_surface:
            self.screen.blit(self.map_surface, (0, 0))

        # Draw walkable debug overlay
        self._draw_walkable_debug()

        # Draw players in front of map
        for player in players_front:
            player.draw(self.screen)
        
        # Draw hazards
        self.hazard_manager.draw(self.screen)
        
        # Draw HUD
        self.hud.draw(self.screen)
        
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
        
        # Eliminate player after drowning
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
        
        # Reset all systems
        self.tile_grid.reset()
        self.hazard_manager.reset()
        self.hud.reset()
        
        # Reset all players
        for player in self.players:
            player.reset()
        
        # Update HUD
        self.hud.set_player_info(self.player_name, len(self.players), len(self.players))

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


# Backward compatibility for older imports.
Game = GameManager
