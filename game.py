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
    PLAYER_START_POS,
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
        slot_count = self._player_slot_count()
        spawn_positions = iter(self._initial_spawns(slot_count))

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
        self._spawn_adjusted = False
        self._spawn_rescue_window = 1.0
        self._time_since_start = 0.0
        self._pending_ai_spawn = False

        if self.game_mode == MODE_VS_COMPUTER:
            primary_char = self._character_choice(0)
            self.players.append(
                Player(
                    position=next(spawn_positions, PLAYER_START_POS),
                    character_name=primary_char,
                )
            )
            if USE_AI_PLAYER:
                self._pending_ai_spawn = True
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
            player1_pos = next(spawn_positions, PLAYER_START_POS)
            player2_pos = next(spawn_positions, PLAYER_START_POS)
            self.players.append(
                Player(
                    position=player1_pos,
                    controls=player1_controls,
                    character_name=self._character_choice(0),
                )
            )
            self.players.append(
                Player(
                    position=player2_pos,
                    controls=player2_controls,
                    character_name=self._character_choice(1),
                )
            )
        else:
            self.players.append(
                Player(
                    position=next(spawn_positions, PLAYER_START_POS),
                    character_name=self._character_choice(0),
                )
            )

        self._ensure_players_on_walkable_surface()
        self._maybe_spawn_pending_ai(initial=True)

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

        self._time_since_start += dt

        # Update game systems
        if not self._spawn_adjusted and self.walkable_mask:
            self._ensure_players_on_walkable_surface()
        self._maybe_spawn_pending_ai()

        self.water.update(dt)
        self.tile_manager.update(dt)

        # Update walkable mask with disappeared/crumbling tiles
        self.walkable_mask = self.tile_manager.get_updated_walkable_mask(self.original_walkable_mask)

        self.hazard_manager.update(dt)
        self.hud.update(dt)

        # Update players
        for player in self.players[:]:
            if player in self.eliminated_players:
                if self._time_since_start <= self._spawn_rescue_window:
                    self.eliminated_players.remove(player)
                    rescued = self._rescue_player_to_safe_tile(player)
                    if rescued:
                        continue
                # Keep updating death animation if active
                if hasattr(player, 'state') and player.state == "death":
                    player._update_death(dt)
                continue

            was_falling_before = player.is_falling()

            if player.is_ai:
                player.update_ai(dt, self.walkable_mask, self.walkable_bounds)
            else:
                player.update(dt, keys, self.walkable_mask, self.walkable_bounds)

            just_started_falling = not was_falling_before and player.is_falling()
            rescued = False
            if self._time_since_start <= self._spawn_rescue_window and player.is_falling():
                rescued = self._rescue_player_to_safe_tile(player)
                if rescued:
                    continue

            # Play fall sound when player starts falling
            if just_started_falling and not rescued:
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

    def _ensure_players_on_walkable_surface(self):
        """Make sure every player spawn point is on a valid tile before play starts."""
        if not self.walkable_mask:
            return

        occupied: set[tuple[int, int]] = set()
        walkable_center = self._walkable_center()
        for player in self.players:
            desired = (int(round(player.position.x)), int(round(player.position.y)))
            if desired in occupied or not self._is_spawn_position_valid(player, desired):
                desired = self._find_valid_fallback(player, occupied, walkable_center)
            self._apply_spawn_position(player, desired)
            occupied.add(desired)
        self._align_ai_spawn_with_human()
        self._spawn_adjusted = True

    def _is_spawn_position_valid(self, player, position: tuple[int, int]) -> bool:
        return player._is_over_platform(pygame.Vector2(position), self.walkable_mask)

    def _find_valid_fallback(
        self,
        player,
        occupied: set[tuple[int, int]],
        origin: pygame.Vector2,
    ) -> tuple[int, int]:
        step_radius = 20
        max_radius = 400
        angle_step = 15
        for radius in range(0, max_radius + step_radius, step_radius):
            for angle_deg in range(0, 360, angle_step):
                angle_rad = math.radians(angle_deg)
                offset = pygame.Vector2(math.cos(angle_rad), math.sin(angle_rad)) * radius
                candidate = (int(round(origin.x + offset.x)), int(round(origin.y + offset.y)))
                if candidate in occupied:
                    continue
                if self._is_spawn_position_valid(player, candidate):
                    return candidate
        return (int(round(origin.x)), int(round(origin.y)))

    def _apply_spawn_position(self, player, position: tuple[int, int]):
        player.position = pygame.Vector2(position)
        player.spawn_position = pygame.Vector2(position)
        player.rect.center = position

    def _walkable_center(self) -> pygame.Vector2:
        if self.walkable_bounds and self.walkable_bounds.width > 0 and self.walkable_bounds.height > 0:
            return pygame.Vector2(self.walkable_bounds.center)
        return pygame.Vector2(PLAYER_START_POS)

    def _align_ai_spawn_with_human(self):
        if not self.walkable_mask:
            return
        human = next((p for p in self.players if not getattr(p, "is_ai", False)), None)
        ai_players = [p for p in self.players if getattr(p, "is_ai", False)]
        if human is None or not ai_players:
            return

        human_origin = pygame.Vector2(round(human.position.x), round(human.position.y))
        base_occupied = {
            (int(round(p.position.x)), int(round(p.position.y)))
            for p in self.players
            if not getattr(p, "is_ai", False)
        }

        for ai in ai_players:
            occupied = base_occupied.copy()
            for other_ai in ai_players:
                if other_ai is ai:
                    continue
                occupied.add((int(round(other_ai.position.x)), int(round(other_ai.position.y))))
            target = self._find_valid_fallback(ai, occupied, human_origin)
            if target:
                self._apply_spawn_position(ai, target)
                base_occupied.add(target)

    def _maybe_spawn_pending_ai(self, initial: bool = False):
        if not self._pending_ai_spawn:
            return
        if not self.walkable_mask:
            return
        human = next((p for p in self.players if not getattr(p, "is_ai", False)), None)
        if human is None:
            return

        ai_player = AIPlayer(position=human.position)
        occupied = {
            (int(round(p.position.x)), int(round(p.position.y)))
            for p in self.players
        }
        origin = pygame.Vector2(round(human.position.x), round(human.position.y))
        target = self._find_valid_fallback(ai_player, occupied, origin)
        self._apply_spawn_position(ai_player, target)
        self.players.append(ai_player)
        self._pending_ai_spawn = False
        self._align_ai_spawn_with_human()
        if not initial:
            alive_count = len(self.players) - len(self.eliminated_players)
            self.hud.set_player_info(self.player_name, alive_count, len(self.players))

    def _rescue_player_to_safe_tile(self, player) -> bool:
        if not self.walkable_mask:
            return False
        occupied = {
            (int(round(p.position.x)), int(round(p.position.y)))
            for p in self.players
            if p is not player and p not in self.eliminated_players
        }
        walkable_center = self._walkable_center()
        safe_position = self._find_valid_fallback(player, occupied, walkable_center)
        if not safe_position:
            return False
        self._apply_spawn_position(player, safe_position)
        player.falling = False
        player.fall_velocity = 0.0
        player.drowning = False
        player.drown_animation_done = False
        player.drown_surface_y = None
        player.jumping = False
        player.z = 0.0
        player.z_velocity = 0.0
        player.on_ground = True
        player.velocity.update(0, 0)
        if hasattr(player, "_set_state"):
            player._set_state("idle", player.facing)
        return True

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
            # Trigger death state if available
            if hasattr(player, 'die'):
                player.die()

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
        self._spawn_adjusted = False
        self._time_since_start = 0.0

        for player in self.players:
            player.reset()

        self._ensure_players_on_walkable_surface()
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

    def _player_slot_count(self) -> int:
        if self.game_mode == MODE_LOCAL_MULTIPLAYER:
            return max(2, len(self.selected_characters))
        if self.game_mode == MODE_VS_COMPUTER:
            human_slots = max(1, len(self.selected_characters))
            return human_slots + (1 if USE_AI_PLAYER else 0)
        return max(1, len(self.selected_characters))

    def _spawn_positions(self, count: int) -> list[tuple[int, int]]:
        center = pygame.Vector2(PLAYER_START_POS)
        if count <= 1:
            return [(int(center.x), int(center.y))]

        radius = 120
        angle_step = (2 * math.pi) / count
        positions: list[tuple[int, int]] = []
        for idx in range(count):
            angle = idx * angle_step
            offset = pygame.Vector2(math.cos(angle), math.sin(angle)) * radius
            pos = center + offset
            positions.append((int(pos.x), int(pos.y)))
        return positions

    def _vs_computer_spawns(self, count: int) -> list[tuple[int, int]]:
        center = pygame.Vector2(PLAYER_START_POS)
        offsets = [
            pygame.Vector2(-90, 0),
            pygame.Vector2(90, 0),
            pygame.Vector2(0, -90),
            pygame.Vector2(0, 90),
            pygame.Vector2(-130, -60),
            pygame.Vector2(130, -60),
            pygame.Vector2(-130, 60),
            pygame.Vector2(130, 60),
        ]
        if count <= len(offsets):
            positions: list[tuple[int, int]] = []
            for idx in range(count):
                pos = center + offsets[idx]
                positions.append((int(round(pos.x)), int(round(pos.y))))
            return positions
        return self._spawn_positions(count)

    def _initial_spawns(self, count: int) -> list[tuple[int, int]]:
        if self.game_mode == MODE_VS_COMPUTER:
            return self._vs_computer_spawns(count)
        return self._spawn_positions(count)

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
