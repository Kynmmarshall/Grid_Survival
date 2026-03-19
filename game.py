import math
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
    SOUND_PLAYER_ELIMINATED,
    SOUND_PLAYER_VICTORY,
    SOUND_SPLASH,
    LEVEL_CONFIG,
    MAX_LEVEL,
    LEVEL_UP_TIME,
    LEVEL_UP_SCORE,
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

        # Level system
        self.current_level = 1
        self.level_config = LEVEL_CONFIG[1].copy()
        self.level_up_pending = False

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
        # Apply level configuration to tile manager
        self._apply_level_config()

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
            self.players.append(Player(character_name=primary_char, player_index=0))
            if USE_AI_PLAYER:
                self.players.append(AIPlayer())
        elif self.game_mode == MODE_LOCAL_MULTIPLAYER:
            player1_controls = {
                'up': pygame.K_w,
                'down': pygame.K_s,
                'left': pygame.K_a,
                'right': pygame.K_d,
                'jump': pygame.K_SPACE,
                'power': pygame.K_q,
            }
            player2_controls = {
                'up': pygame.K_UP,
                'down': pygame.K_DOWN,
                'left': pygame.K_LEFT,
                'right': pygame.K_RIGHT,
                'jump': pygame.K_RSHIFT,
                'power': pygame.K_p,
            }
            self.players.append(
                Player(controls=player1_controls, character_name=self._character_choice(0), player_index=0)
            )
            self.players.append(
                Player(controls=player2_controls, character_name=self._character_choice(1), player_index=1)
            )
        else:
            self.players.append(Player(character_name=self._character_choice(0), player_index=0))

        # Get main player's health
        player_health = 0
        player_max_health = 0
        for p in self.players:
            if hasattr(p, 'health'):
                player_health = p.health
                player_max_health = p.max_health
                break
        level_name = self.level_config.get("name", "")
        self.hud.set_player_info(player_name, len(self.players), len(self.players), player_health, player_max_health, self.current_level, level_name)

        self.game_over = False
        self.audio = get_audio()
        self.audio.play_music()
        # Preload all SFX into the cache now so the first play never hitches
        self.audio.preload_directory()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
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

        # Check for level up
        self._check_level_up()

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

            # Reset per-frame immunity flag before power apply
            if hasattr(player, '_immune_to_hazards'):
                player._immune_to_hazards = False

            was_falling_before = player.is_falling()

            if player.is_ai:
                player.update_ai(dt, self.walkable_mask, self.walkable_bounds)
            else:
                player.update(dt, keys, self.walkable_mask, self.walkable_bounds)

            # Let the player's power interact with the game world
            if hasattr(player, 'power'):
                player.power.apply_to_game(self)

            # Play fall sound when player starts falling
            if not was_falling_before and player.is_falling():
                self.audio.play_sfx(SOUND_PLAYER_FALL)

            # Check water contact
            self._check_water_contact(player)

            # Check hazard collisions — skip if power grants immunity
            immune = getattr(player, '_immune_to_hazards', False)
            if not immune and self.hazard_manager.check_player_collision(player):
                # Give robots a chance to absorb the hit via their armour passive
                absorbed = False
                if hasattr(player, 'power') and hasattr(player.power, 'on_hazard_hit'):
                    absorbed = player.power.on_hazard_hit()
                if not absorbed:
                    # Reduce health instead of immediate elimination
                    if hasattr(player, 'health'):
                        player.health -= 1
                        if player.health <= 0:
                            self._eliminate_player(player, "hit by hazard")
                    else:
                        self._eliminate_player(player, "hit by hazard")

            # Check if player fell off screen
            if player.position.y > WINDOW_SIZE[1] + 100:
                self._eliminate_player(player, "fell off")

        # Update player count in HUD
        alive_count = len(self.players) - len(self.eliminated_players)
        # Get main player's health
        player_health = 0
        player_max_health = 0
        for p in self.players:
            if hasattr(p, 'health'):
                player_health = p.health
                player_max_health = p.max_health
                break
        level_name = self.level_config.get("name", "")
        self.hud.set_player_info(self.player_name, alive_count, len(self.players), player_health, player_max_health, self.current_level, level_name)

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
        self.hud.draw(self.screen)

        # Draw per-player power indicators
        self._draw_power_hud()

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
        self.audio.play_sfx(SOUND_SPLASH, volume=0.70, volume_jitter=0.08, max_instances=2)

        if player not in self.eliminated_players:
            self._eliminate_player(player, "drowned")

    def _eliminate_player(self, player, reason: str):
        """Mark a player as eliminated."""
        if player not in self.eliminated_players:
            self.eliminated_players.append(player)
            self.audio.play_sfx(SOUND_PLAYER_ELIMINATED, volume=0.80, max_instances=2)
            print(f"Player eliminated: {reason}")

    def _trigger_game_over(self):
        """Trigger game over state."""
        if not self.game_over:
            self.game_over = True
            # Determine if there's a surviving winner (multiplayer) or everyone lost
            alive = [p for p in self.players if p not in self.eliminated_players]
            if alive:
                self.audio.play_sfx(SOUND_PLAYER_VICTORY, volume=0.85, max_instances=1)
            self.elimination_screen = EliminationScreen(
                self.player_name,
                self.hud.survival_time,
                self.hud.score,
                "eliminated"
            )
            self.elimination_screen.show()

    def _apply_level_config(self):
        """Apply the current level configuration to tile manager."""
        self.tile_manager.base_disappear_interval = self.level_config["disappear_interval"]
        self.tile_manager.min_disappear_interval = self.level_config["min_interval"]
        self.tile_manager.simultaneous_tiles = self.level_config["simultaneous_tiles"]
        self.tile_manager.grace_period = self.level_config["grace_period"]
        # Reset interval to base
        self.tile_manager.current_interval = self.level_config["disappear_interval"]

    def _check_level_up(self):
        """Check if player has survived long enough to level up."""
        if self.current_level >= MAX_LEVEL:
            return

        # Level up by survival time
        survival_time = self.hud.survival_time
        time_threshold = self.current_level * LEVEL_UP_TIME

        if survival_time >= time_threshold:
            self._level_up()

    def _level_up(self):
        """Level up the game difficulty."""
        if self.current_level >= MAX_LEVEL:
            return

        self.current_level += 1
        self.level_config = LEVEL_CONFIG[self.current_level].copy()
        self._apply_level_config()
        print(f"Level Up! Now at level {self.current_level}: {self.level_config['name']}")

    def _restart_game(self):
        """Restart the game."""
        self.game_over = False
        self.elimination_screen = None
        self.eliminated_players.clear()

        # Reset level
        self.current_level = 1
        self.level_config = LEVEL_CONFIG[1].copy()

        self.tile_manager.reset()
        self.walkable_mask = self.original_walkable_mask.copy() if self.original_walkable_mask else None
        self.hazard_manager.reset()
        self.hud.reset()

        for player in self.players:
            player.reset()

        # Get main player's health
        player_health = 0
        player_max_health = 0
        for p in self.players:
            if hasattr(p, 'health'):
                player_health = p.health
                player_max_health = p.max_health
                break
        level_name = self.level_config.get("name", "")
        self.hud.set_player_info(self.player_name, len(self.players), len(self.players), player_health, player_max_health, self.current_level, level_name)

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

    def _draw_power_hud(self):
        """Draw each human player's power icon, name, and cooldown ring at bottom of screen."""
        try:
            font_name = pygame.font.SysFont("consolas", 13)
            font_key  = pygame.font.SysFont("consolas", 11)
        except Exception:
            return

        human_players = [p for p in self.players if not p.is_ai]
        icon_size = 44
        padding = 12
        total_w = len(human_players) * (icon_size + padding * 2 + 120)
        start_x = WINDOW_SIZE[0] // 2 - total_w // 2

        for idx, player in enumerate(human_players):
            if not hasattr(player, 'power'):
                continue
            power = player.power
            bx = start_x + idx * (icon_size + padding * 2 + 130)
            by = WINDOW_SIZE[1] - icon_size - 18

            # Background panel
            panel_w = icon_size + padding * 2 + 124
            panel_rect = pygame.Rect(bx - 6, by - 6, panel_w, icon_size + 12)
            panel_surf = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
            panel_surf.fill((10, 10, 20, 170))
            pygame.draw.rect(panel_surf, (*power.COLOR, 160),
                             panel_surf.get_rect(), 2, border_radius=8)
            self.screen.blit(panel_surf, panel_rect.topleft)

            # Icon circle
            icon_rect = pygame.Rect(bx, by, icon_size, icon_size)
            power.draw_hud_icon(self.screen, icon_rect)

            # Cooldown arc overlay on icon
            if power.cooldown_remaining > 0:
                frac = power.cooldown_fraction
                arc_rect = pygame.Rect(bx - 2, by - 2, icon_size + 4, icon_size + 4)
                pygame.draw.arc(self.screen, (255, 255, 255),
                                arc_rect,
                                math.pi / 2,
                                math.pi / 2 + math.tau * frac,
                                3)

            # Power name and description
            tx = bx + icon_size + 8
            name_surf = font_name.render(power.NAME, True, power.COLOR)
            self.screen.blit(name_surf, (tx, by + 2))

            desc_color = (160, 160, 170)
            desc_surf = font_name.render(power.DESCRIPTION[:32], True, desc_color)
            self.screen.blit(desc_surf, (tx, by + 18))

            # Key hint
            key_name = pygame.key.name(player.controls.get('power', 0)).upper()
            status = "READY" if power.ready else (
                f"{power.cooldown_remaining:.1f}s" if not power.active else "ACTIVE"
            )
            status_color = (80, 255, 120) if power.ready else (
                (255, 220, 60) if power.active else (180, 180, 180)
            )
            key_surf = font_key.render(f"[{key_name}] {status}", True, status_color)
            self.screen.blit(key_surf, (tx, by + 32))

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