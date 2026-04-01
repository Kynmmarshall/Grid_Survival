import math

import pygame

from ai_player import AIPlayer
from assets import load_background_surface, load_tilemap_surface
from audio import get_audio
from collision_manager import CollisionManager
from player import Player
from orbs import OrbManager
from powers import get_power_for_character, power_key_for_player
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
        network=None,
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
        self.network = network
        
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
        
        # Calculate spawn points after map loads
        slot_count = self._player_slot_count()
        spawn_positions = iter(self._initial_spawns(slot_count))
        
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
        self.orb_manager = OrbManager()

        # Initialize players based on game mode
        self.players = []
        self.eliminated_players = []
        self.elimination_screen = None
        self._spawn_adjusted = False
        self._spawn_rescue_window = 1.0
        self._time_since_start = 0.0
        self._pending_initial_restart = (self.game_mode == MODE_VS_COMPUTER and USE_AI_PLAYER)
        if self.game_mode == MODE_VS_COMPUTER:
            primary_char = self._character_choice(0)
            self.players.append(
                Player(
                    position=next(spawn_positions, PLAYER_START_POS),
                    character_name=primary_char,
                )
            )
            if USE_AI_PLAYER:
                ai_pos = next(spawn_positions, PLAYER_START_POS)
                self.players.append(AIPlayer(position=ai_pos))
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
                'power': pygame.K_SLASH,
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
        self._force_safe_spawns()
        self._configure_powers_for_players()

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
                else:
                    self._handle_power_key(event.key)

    def update(self, dt: float, keys):
        if keys[pygame.K_ESCAPE]:
            self.running = False
            return

        # Hidden first-frame restart to ensure AI is visible on first launch
        if self._pending_initial_restart:
            self._pending_initial_restart = False
            self._restart_game()
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
        for player in self.players:
            player._immune_to_hazards = False

        # --- LAN Multiplayer Sync ---
        if self.network:
            # Assume 2 players: local is index 0, remote is index 1
            from network import PlayerState
            # Send local player state
            local_player = self.players[0]
            local_state = PlayerState(
                x=local_player.position.x,
                y=local_player.position.y,
                facing=getattr(local_player, 'facing', 'down'),
                state=getattr(local_player, 'state', 'idle'),
                falling=getattr(local_player, 'falling', False),
                drowning=getattr(local_player, 'drowning', False),
                eliminated=local_player in self.eliminated_players,
            )
            self.network.send_player_state("0", local_state)
            # Receive remote player state
            messages = self.network.get_messages()
            for msg in messages:
                if msg.get('type') == 'player_state' and len(self.players) > 1:
                    idx = 1 if msg['player_id'] == '1' else 0
                    if idx < len(self.players):
                        remote = self.players[idx]
                        s = msg['state']
                        remote.position.x = s['x']
                        remote.position.y = s['y']
                        remote.facing = s['facing']
                        remote.state = s['state']
                        remote.falling = s['falling']
                        remote.drowning = s['drowning']
                        if s['eliminated'] and remote not in self.eliminated_players:
                            self.eliminated_players.append(remote)

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

            if player.power:
                player.power.update(dt, player)

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

        for player in self.players:
            if player in self.eliminated_players:
                continue
            if player.power:
                player.power.apply_to_game(self)

        self.orb_manager.update(dt, self.walkable_bounds, self.players, self)

        # Update player count in HUD
        alive_count = len(self.players) - len(self.eliminated_players)
        self.hud.set_player_info(self.player_name, alive_count, len(self.players))

        # Check game over condition — either everyone eliminated or no one remains on the platform.
        platform_empty = not self._any_player_on_platform()
        if alive_count == 0 or platform_empty:
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

        # Draw orbs floating above the arena
        self.orb_manager.draw(self.screen)

        # Draw players in front of map
        for player in players_front:
            player.draw(self.screen)

        # Draw hazards
        self.hazard_manager.draw(self.screen)

        # Draw active power visuals
        for player in self.players:
            if player in self.eliminated_players:
                continue
            if player.power:
                player.power.draw(self.screen, player)

        # Draw HUD
        self.hud.draw(self.screen, self.players, is_muted=self.audio.is_muted)

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
        return

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
        if self._can_block_elimination(player, reason):
            return
        if player not in self.eliminated_players:
            self.eliminated_players.append(player)
            print(f"Player eliminated: {reason}")
            # Trigger death state if available
            if hasattr(player, 'die'):
                player.die()

    def _any_player_on_platform(self) -> bool:
        for player in self.players:
            if player in self.eliminated_players:
                continue
            if self._player_on_platform(player):
                return True
        return False

    def _player_on_platform(self, player) -> bool:
        if player.is_falling() or player.is_drowning():
            return False
        mask = self.walkable_mask
        if mask is None:
            return True
        try:
            return player._is_over_platform(player.position, mask)
        except AttributeError:
            return False

    def _can_block_elimination(self, player, reason: str) -> bool:
        hazard_reasons = {"hit by hazard", "fell off"}
        if reason in hazard_reasons and hasattr(player, "has_active_shield"):
            if player.has_active_shield():
                return True
        if reason == "hit by hazard" and getattr(player, "_immune_to_hazards", False):
            return True
        if reason == "hit by hazard" and getattr(player, "power", None):
            on_hit = getattr(player.power, "on_hazard_hit", None)
            if callable(on_hit) and on_hit():
                return True
        return False

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
        self.orb_manager.reset()
        self.hud.reset()
        self._spawn_adjusted = False
        self._time_since_start = 0.0

        for player in self.players:
            player.reset()
            if player.power:
                player.power.reset()

        self._ensure_players_on_walkable_surface()
        self._force_safe_spawns()
        self._configure_powers_for_players()
        self.hud.set_player_info(self.player_name, len(self.players), len(self.players))

    def _force_safe_spawns(self):
        """Clamp every player to a valid walkable tile and clear fall/drown flags."""
        if not self.walkable_mask:
            return
        center = self._walkable_center()
        safe = (int(round(center.x)), int(round(center.y)))
        for player in self.players:
            pos_tuple = (int(round(player.position.x)), int(round(player.position.y)))
            if not self._is_spawn_position_valid(player, pos_tuple):
                self._apply_spawn_position(player, safe)
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

    def _draw_tmx_map_with_tiles(self):
        """Draw TMX map layers, letting missing tiles reveal the background."""
        if not self.tmx_data or not self.map_surface:
            return

        # self.map_surface contains non-destructible layers (Bottom)
        # We need to ensure that the platform tiles (Top) are drawn by tile_manager
        # and that the background (starry void) is visible where platform tiles are missing.
        
        # 1. Draw static background/bottom layers
        self.screen.blit(self.map_surface, (0, 0))

        # 2. Draw active platform tiles (destructible)
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

    def _configure_powers_for_players(self):
        for idx, player in enumerate(self.players):
            self._configure_power_for_player(player, idx)

    def _configure_power_for_player(self, player, slot_index: int):
        if getattr(player, "power", None):
            return
        character = getattr(player, "character_name", None)
        power = get_power_for_character(character)
        key = None
        if not getattr(player, "is_ai", False):
            controls = getattr(player, "controls", None)
            override = None
            if isinstance(controls, dict):
                override = controls.get('power')
            key = override or power_key_for_player(slot_index)
        player.attach_power(power, key)

    def _handle_power_key(self, key: int):
        for player in self.players:
            if player in self.eliminated_players:
                continue
            if getattr(player, "power_key", None) == key:
                if player.try_use_power():
                    break

    def _initial_spawns(self, slot_count: int) -> list[tuple[int, int]]:
        # Hardcoded grid positions on the platform (10x6 platform at x=7, y=9)
        # Platform center is approx (12, 12)
        grid_spots = [
            (11, 12), # P1
            (14, 12), # P2
            (12, 11), # P3
            (12, 13), # P4
        ]
        
        spawns = []
        for i in range(slot_count):
            if i < len(grid_spots):
                gx, gy = grid_spots[i]
                pos = self._grid_to_screen(gx, gy)
            else:
                 # Fallback to center
                 pos = self._grid_to_screen(12, 12)
            spawns.append(pos)
        return spawns

    def _grid_to_screen(self, gx: int, gy: int) -> tuple[int, int]:
        """Convert grid coordinates to screen pixel coordinates."""
        if not self.tmx_data:
            return PLAYER_START_POS
            
        half_width = self.tmx_data.tilewidth / 2
        half_height = self.tmx_data.tileheight / 2
        
        # Iso projection logic (matching TMX rendering)
        # origin_x is likely map_height * half_width based on standard staggered
        origin_x = self.tmx_data.height * half_width
        
        # Calculate pixel from grid
        pixel_x = (gx - gy) * half_width + origin_x
        pixel_y = (gx + gy) * half_height
        
        # Adjust to center of tile surface (top-center of diamond)
        # Tiled places image top-left at pixel_x, pixel_y usually
        # Actually Tiled staggered iso uses center-bottom alignment for objects?
        # But for tiles, it draws tile image at calculated pos.
        # Let's target the center of the diamond.
        center_x = pixel_x + half_width
        center_y = pixel_y + half_height
        
        # Apply global map scale and offset
        # Offset is (window_w - scaled_w)//2, (window_h - scaled_h)//2
        off_x, off_y = (0, 0)
        if self.map_offset:
            off_x, off_y = self.map_offset
            
        screen_x = center_x * self.map_scale_x + off_x
        screen_y = center_y * self.map_scale_y + off_y
        
        # Adjust Y slightly up because "standing on top"
        # Since tiles have height (like 128px image vs 64px grid height),
        # the surface is usually visually higher.
        # But our current tiles are just flat diamonds mostly?
        # The tileset tilesfloorbig uses 128x128 images but tileheight 64.
        # This implies a lot of vertical space. 
        # Typically the "visual top" is higher up.
        # Let's shift Y up by say 32 pixels to be safe.
        screen_y -= 16

        return (int(screen_x), int(screen_y))

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
