import math
import random
import threading
import time
from pathlib import Path
from typing import Any

import pygame

from backend.account_service import AccountService
from ai_player import AIPlayer
from assets import load_background_surface, load_tilemap_surface
from audio import get_audio
from collision_manager import CollisionManager
from player import Player
from post_match_ui import MatchSummaryScreen, RRGainScreen
from orbs import OrbManager
from pacman_enemies import PacmanEnemyManager
from powers import (
    apply_power_state,
    get_power_for_character,
    power_key_for_player,
    snapshot_power_state,
)
from water import AnimatedWater
from tile_system import TMXTileManager, TileState
from hazards import HazardManager
from ui import GameHUD, EliminationScreen, VictoryScreen
from scenes.common import draw_online_status_badge, update_online_status
from settings import (
    BACKGROUND_COLOR,
    BACKGROUND_MUSIC_TRACKS,
    AUDIO_VOLUME_STEP,
    DEBUG_DRAW_WALKABLE,
    DEBUG_VISUALS_ENABLED,
    DEBUG_WALKABLE_COLOR,
    MODE_CAMPAIGN,
    MODE_LOCAL_MULTIPLAYER,
    MODE_ONLINE_MULTIPLAYER,
    PLAYER_START_POS,
    TARGET_FPS,
    WINDOW_FLAGS,
    USE_AI_PLAYER,
    WINDOW_SIZE,
    WINDOW_TITLE,
    SOUND_PLAYER_FALL,
    DEFAULT_CONTROLS,
    load_custom_controls,
)


class GameManager:
    """Main game application wrapper with full feature integration."""

    def __init__(
        self,
        screen=None,
        clock=None,
        player_name: str = "Player",
        game_mode: str = MODE_CAMPAIGN,
        selected_characters: list[str] | None = None,
        network=None,
        local_player_index: int = 0,
        level_map_path: str | Path | None = None,
        level_background_path: str | Path | None = None,
        target_score: int = 3,
        account_service: AccountService | None = None,
        account_username: str | None = None,
        network_player_names: list[str] | None = None,
        ranked_override: bool | None = None,
    ):
        if screen is None or clock is None:
            pygame.init()
        self.screen = screen or pygame.display.set_mode(WINDOW_SIZE, WINDOW_FLAGS)
        pygame.display.set_caption(WINDOW_TITLE)
        self.clock = clock or pygame.time.Clock()
        self.running = True
        self.player_name = player_name
        self.game_mode = game_mode
        self.paused = False
        self.selected_characters = selected_characters or []
        self.account_service = account_service
        self.account_username = (account_username or "").strip() or None
        self.network_player_names = [str(name) for name in (network_player_names or [])]
        self._ranked_override = None if ranked_override is None else bool(ranked_override)
        self._guest_rr = 1000
        self._match_result_serial = 0
        self._last_applied_match_result_id: str | None = None
        if self.account_service and self.account_username:
            profile = self.account_service.get_profile(self.account_username)
            if profile is not None:
                self._guest_rr = int(profile.rr)
        self._match_rr_start = int(self._guest_rr)
        self.network = network
        self.is_network_game = (
            self.game_mode == MODE_ONLINE_MULTIPLAYER and self.network is not None
        )
        self.is_network_host = bool(self.is_network_game and getattr(self.network, "is_host", False))
        self.local_player_index = 0 if not self.is_network_game else max(0, min(1, local_player_index))
        self.remote_player_index = 1 - self.local_player_index if self.is_network_game else None
        self._pending_power_press = False
        self._pending_remote_power_uses = 0
        self._remote_input_state = self._empty_network_input_state()
        self._authoritative_network_inputs = None
        self._snapshot_send_timer = 1 / 60
        self._snapshot_interval = 1 / 60
        self._world_dynamic_snapshot_send_timer = 0.0
        self._world_dynamic_snapshot_interval = 1 / 30
        self._world_snapshot_send_timer = 0.0
        self._world_snapshot_interval = 1 / 20
        self._network_round_seq = 0
        self._last_client_snapshot_time = -1.0
        self._last_client_world_snapshot_time = -1.0
        self._last_client_world_dynamic_snapshot_time = -1.0
        self._last_client_tile_snapshot_time = -1.0
        self._last_client_hazard_snapshot_time = -1.0
        self._last_client_orb_snapshot_time = -1.0
        self._last_client_pacman_snapshot_time = -1.0
        self._last_client_snapshot_round_seq = -1
        self._last_client_world_snapshot_round_seq = -1
        self._client_position_blend = 0.35
        self._client_local_position_blend = 0.22
        self._client_local_reconcile_deadzone = 12.0
        self._client_last_local_input = self._empty_network_input_state()
        self._client_snap_distance = 180.0
        self._client_snapshot_gap = self._snapshot_interval
        self._client_prediction_enabled = True
        self._client_remote_extrapolation_cap = 1 / 16
        self._network_disconnect_started_at: float | None = None
        self._network_last_reconnect_attempt_at = 0.0
        self._network_reconnect_thread: threading.Thread | None = None
        # Rate-limiting for client input messages: only send when the state
        # changes or when the minimum interval has elapsed (60 Hz cap).
        self._input_send_timer: float = 0.0
        self._input_send_interval: float = 1 / 60
        self._last_sent_input: dict | None = None
        self.level_map_path = Path(level_map_path) if level_map_path else None
        self.level_background_path = Path(level_background_path) if level_background_path else None
        self.target_score = max(1, int(target_score))
        self.round_wins: list[int] = []
        self._round_restart_delay = 2.0
        self._round_restart_timer = 0.0
        self._match_complete = False
        self._round_transition_seen = False
        self._match_player_labels: list[str] = []
        self._match_player_stats: list[dict] = []
        
        # Load assets
        self.background_surface = load_background_surface(
            WINDOW_SIZE,
            self.level_background_path,
        )
        (
            self.map_surface,
            self.tmx_data,
            self.walkable_mask,
            self.walkable_bounds,
            self.map_scale_x,
            self.map_scale_y,
            self.map_offset,
        ) = load_tilemap_surface(WINDOW_SIZE, self.level_map_path)
        
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
        self.pacman_enemy_manager = None

        # Initialize players based on game mode
        self.players = []
        self.eliminated_players = []
        self.elimination_screen = None
        self.victory_screen = None
        self.game_over_state = None
        self._spawn_adjusted = False
        self._spawn_rescue_window = 1.0
        self._time_since_start = 0.0
        self._pending_initial_restart = (self.game_mode == MODE_CAMPAIGN and USE_AI_PLAYER)
        if self.game_mode == MODE_CAMPAIGN:
            custom_controls = load_custom_controls()
            if custom_controls is None:
                custom_controls = {
                    "player1": dict(DEFAULT_CONTROLS["player1"]),
                    "player2": dict(DEFAULT_CONTROLS["player2"]),
                }
            player1_controls = dict(custom_controls.get("player1", DEFAULT_CONTROLS["player1"]))
            primary_char = self._character_choice(0)
            self.players.append(
                Player(
                    position=next(spawn_positions, PLAYER_START_POS),
                    controls=player1_controls,
                    character_name=primary_char,
                )
            )
            if USE_AI_PLAYER:
                ai_pos = next(spawn_positions, PLAYER_START_POS)
                self.players.append(AIPlayer(position=ai_pos))
        elif self.game_mode == MODE_LOCAL_MULTIPLAYER:
            custom_controls = load_custom_controls()
            if custom_controls is None:
                custom_controls = {
                    key: dict(value)
                    for key, value in DEFAULT_CONTROLS.items()
                }

            for idx in range(2):
                control_key = f"player{idx + 1}"
                controls = dict(
                    custom_controls.get(
                        control_key,
                        DEFAULT_CONTROLS.get(control_key, DEFAULT_CONTROLS["player1"]),
                    )
                )
                self.players.append(
                    Player(
                        position=next(spawn_positions, PLAYER_START_POS),
                        controls=controls,
                        character_name=self._character_choice(idx),
                    )
                )
        elif self.is_network_game:
            custom_controls = load_custom_controls()
            if custom_controls is None:
                custom_controls = {
                    "player1": dict(DEFAULT_CONTROLS["player1"]),
                    "player2": dict(DEFAULT_CONTROLS["player2"]),
                }
            local_controls = custom_controls["player1"]
            remote_controls = custom_controls["player2"]
            for idx in range(2):
                controls = local_controls if idx == self.local_player_index else remote_controls
                self.players.append(
                    Player(
                        position=next(spawn_positions, PLAYER_START_POS),
                        controls=controls,
                        character_name=self._character_choice(idx),
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
        enemy_count = self._pacman_enemy_count()
        if enemy_count > 0:
            enemy_spawns = self._initial_pacman_enemy_spawns(enemy_count)
            self.pacman_enemy_manager = PacmanEnemyManager(enemy_spawns)

        self.round_wins = [0 for _ in self.players]
        self._match_player_labels = [self._resolve_player_label(idx) for idx in range(len(self.players))]
        self._match_player_stats = [self._new_match_stat_row(idx) for idx in range(len(self.players))]
        self.hud.set_player_info(player_name, len(self.players), len(self.players))
        self.hud.set_round_scoreboard(self.round_wins, self.target_score)

        self.game_over = False
        self.audio = get_audio()
        self.audio.play_music_playlist(
            BACKGROUND_MUSIC_TRACKS,
            start_random=True,
            loop=True,
            fade_ms=1500,
        )

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:  # Left click
                    if self.hud.pause_rect and self.hud.pause_rect.collidepoint(event.pos):
                        self._toggle_pause()
                        continue
                    if self.hud.mute_rect and self.hud.mute_rect.collidepoint(event.pos):
                        self.audio.toggle_mute()
                    elif self._handle_ninja_target_click(event.pos):
                        continue
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_PAGEUP, pygame.K_EQUALS, pygame.K_KP_PLUS, pygame.K_RIGHTBRACKET):
                    self._adjust_audio_volume(AUDIO_VOLUME_STEP)
                    continue
                if event.key in (pygame.K_PAGEDOWN, pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_LEFTBRACKET):
                    self._adjust_audio_volume(-AUDIO_VOLUME_STEP)
                    continue
                if event.key == pygame.K_TAB:
                    self._toggle_pause()
                    continue
                elif event.key == pygame.K_l and not self.is_network_game:
                    for player in self.players:
                        player.reset()
                elif event.key == pygame.K_r and self.game_over:
                    if not self._can_use_end_of_match_actions():
                        continue
                    reset_match = bool(self._match_complete)
                    if self.is_network_game:
                        if self.is_network_host:
                            self._restart_network_round(reset_match=reset_match)
                        elif self.network and self.network.connected:
                            self.network.send_message("restart_request", reset_match=reset_match)
                    else:
                        self._restart_game(reset_match=reset_match)
                    continue
                else:
                    if self.is_network_game:
                        local_player = self._local_network_player()
                        local_power_key = getattr(local_player, "power_key", None)
                        if local_power_key is not None and event.key == local_power_key:
                            first_press = not self._pending_power_press
                            self._pending_power_press = True
                            if (
                                first_press
                                and not self.is_network_host
                                and self.network
                                and self.network.connected
                            ):
                                self.network.send_message("power_use_request")
                    else:
                        self._handle_power_key(event.key)

    def update(self, dt: float, keys):
        self.audio.update()

        if getattr(self, "paused", False):
            if self.is_network_game and self.network and self.network.connected:
                self._process_network_messages()
                if not self.running or not self.network.connected:
                    return
            if keys[pygame.K_LCTRL]:
                if self.is_network_game and self.network and self.network.connected:
                    self.network.send_message("disconnect")
                self.return_to_main_menu = True
                self.running = False
            return

        if self.is_network_game:
            if not self.network or not self.network.connected:
                now = time.time()
                if self._network_disconnect_started_at is None:
                    self._network_disconnect_started_at = now
                    self._network_last_reconnect_attempt_at = 0.0
                    print(f"[NETWORK] Disconnected at time={self._time_since_start:.1f}s, will attempt reconnect", flush=True)

                disconnect_duration = now - self._network_disconnect_started_at

                if not self._network_reconnect_thread or not self._network_reconnect_thread.is_alive():
                    self._network_reconnect_thread = threading.Thread(
                        target=self._start_network_reconnect_worker,
                        daemon=True,
                    )
                    self._network_reconnect_thread.start()

                # Log disconnect duration
                if int(disconnect_duration) % 5 == 0 and disconnect_duration > 0:
                    print(f"[NETWORK] Disconnected for {disconnect_duration:.1f}s, status=DISCONNECTED, dt={dt:.1f}ms", flush=True)

                if disconnect_duration > 15.0:
                    print(f"[NETWORK] Timeout after {disconnect_duration:.1f}s, exiting", flush=True)
                    self.running = False
                return

            self._network_disconnect_started_at = None
            self._network_last_reconnect_attempt_at = 0.0
            if self._network_reconnect_thread and not self._network_reconnect_thread.is_alive():
                self._network_reconnect_thread = None

            self._process_network_messages()
            if not self.running or not self.network.connected:
                return

            local_input = self._build_local_input_state(keys)
            if self.is_network_host:
                self._snapshot_send_timer += dt
                self._authoritative_network_inputs = {
                    self.local_player_index: local_input,
                    self.remote_player_index: self._remote_input_state,
                }
            else:
                # Rate-limit input messages to 30 Hz and skip identical states.
                # Previously sent every frame (up to 60 Hz), flooding the host
                # with redundant messages it mostly discarded.
                self._input_send_timer += dt
                input_changed = local_input != self._last_sent_input
                if input_changed or self._input_send_timer >= self._input_send_interval:
                    self.network.send_message("input_state", input=local_input)
                    self._last_sent_input = dict(local_input)
                    self._input_send_timer = 0.0
                self._update_client_network_game(dt, local_input)
                self._pending_power_press = False
                return

        # Hidden first-frame restart to ensure AI is visible on first launch
        if self._pending_initial_restart:
            self._pending_initial_restart = False
            self._restart_game(reset_match=True)
            return

        if self.game_over:
            if self._can_use_end_of_match_actions() and keys[pygame.K_LCTRL]:
                if self.is_network_game and self.network and self.network.connected:
                    self.network.send_message("disconnect")
                self.return_to_main_menu = True
                self.running = False

            if self.victory_screen:
                self.victory_screen.update(dt)
            elif self.elimination_screen:
                self.elimination_screen.update(dt)

            if len(self.players) > 1 and not self._match_complete:
                self._round_restart_timer += dt
                if self._round_restart_timer >= self._round_restart_delay:
                    if self.is_network_game:
                        if self.is_network_host:
                            self._restart_network_round(reset_match=False)
                    else:
                        self._restart_game(reset_match=False)
            return

        if getattr(self, "paused", False) or self.paused:
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
            player._eliminated = player in self.eliminated_players

        network_inputs = getattr(self, "_authoritative_network_inputs", None)

        # Update players
        for idx, player in enumerate(self.players[:]):
            if player in self.eliminated_players:
                if self._time_since_start <= self._spawn_rescue_window:
                    self.eliminated_players.remove(player)
                    player._eliminated = False
                    rescued = self._rescue_player_to_safe_tile(player)
                    if rescued:
                        continue
                # Keep updating death animation if active
                if hasattr(player, 'state') and player.state == "death":
                    player._update_death(dt)
                continue

            was_falling_before = player.is_falling()

            if player.is_ai:
                player.update_ai(
                    dt,
                    self.walkable_mask,
                    self.walkable_bounds,
                    self.hazard_manager,
                    self.pacman_enemy_manager,
                )
            elif network_inputs is not None and idx in network_inputs:
                player_input = self._sanitize_network_input(network_inputs[idx])
                power_requested = bool(player_input.get("power_pressed"))
                if (
                    self.is_network_game
                    and self.is_network_host
                    and idx == self.remote_player_index
                    and self._pending_remote_power_uses > 0
                ):
                    power_requested = True
                    self._pending_remote_power_uses = max(0, self._pending_remote_power_uses - 1)
                if power_requested:
                    player.try_use_power(self)
                player.update_from_input_state(
                    dt,
                    player_input,
                    self.walkable_mask,
                    self.walkable_bounds,
                )
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
                # Check for LIFE orb collection before elimination
                self._check_life_orb_collection(player)
                self._eliminate_player(player, "hit by hazard")

            # Check if player fell off screen
            if player.position.y > WINDOW_SIZE[1] + 100:
                # Check for LIFE orb collection before elimination
                self._check_life_orb_collection(player)
                self._eliminate_player(player, "fell off")

        for player in self.players:
            if player in self.eliminated_players:
                continue
            if player.power:
                player.power.apply_to_game(self)

        if self.pacman_enemy_manager:
            ghost_victims = self.pacman_enemy_manager.update(
                dt,
                self.players,
                self.walkable_mask,
                self.walkable_bounds,
            )
            seen_victims: set[int] = set()
            for victim in ghost_victims:
                victim_id = id(victim)
                if victim_id in seen_victims:
                    continue
                seen_victims.add(victim_id)
                self._eliminate_player(victim, "hit by hazard")

        self.orb_manager.update(dt, self.walkable_bounds, self.players, self)

        for idx, player in enumerate(self.players):
            if idx >= len(self._match_player_stats):
                continue
            if player in self.eliminated_players:
                continue
            self._match_player_stats[idx]["survival_time"] += float(dt)

        # Update player count in HUD
        alive_count = len(self.players) - len(self.eliminated_players)
        if alive_count > 1:
            self._round_transition_seen = False
        self.hud.set_player_info(self.player_name, alive_count, len(self.players))

        # Check completion only after elimination animations finish so death sequences play out.
        completion_ready = self._elimination_animations_finished()

        # Victory for the last remaining participant.
        if len(self.players) > 1 and alive_count == 1:
            if completion_ready:
                if self._round_transition_seen:
                    return
                self._round_transition_seen = True
                winner_index = next(
                    (idx for idx, player in enumerate(self.players) if player not in self.eliminated_players),
                    0,
                )
                winner = self.players[winner_index] if self.players else None
                winner_label = getattr(winner, "character_name", self.player_name) if winner else self.player_name
                self._handle_round_victory(winner_index, winner_label)
            return

        # Round draw when everyone is gone in multi-player.
        if alive_count == 0 and completion_ready:
            if len(self.players) > 1:
                if self._round_transition_seen:
                    return
                self._round_transition_seen = True
                self._handle_round_draw()
                return
            self._trigger_game_over()

        for player in self.players:
            player._eliminated = player in self.eliminated_players

        if self.is_network_game and self.is_network_host:
            if self._snapshot_send_timer >= self._snapshot_interval:
                self._snapshot_send_timer = 0.0
                self._world_dynamic_snapshot_send_timer += self._snapshot_interval
                self._world_snapshot_send_timer += self._snapshot_interval
                include_world_dynamic = (
                    self._world_dynamic_snapshot_send_timer >= self._world_dynamic_snapshot_interval
                )
                include_world = self._world_snapshot_send_timer >= self._world_snapshot_interval
                if include_world_dynamic:
                    self._world_dynamic_snapshot_send_timer = 0.0
                if include_world:
                    self._world_snapshot_send_timer = 0.0
                self.network.send_message(
                    "snapshot",
                    state=self._build_network_snapshot(),
                )
                if include_world_dynamic:
                    self.network.send_message(
                        "world_dynamic_snapshot",
                        state=self._build_network_dynamic_world_snapshot(),
                    )
                if include_world:
                    self.network.send_message(
                        "world_snapshot",
                        state=self._build_network_world_snapshot(),
                    )
            self._pending_power_press = False
            self._authoritative_network_inputs = None

    def _update_client_network_game(self, dt: float, local_input: dict | None = None):
        if isinstance(local_input, dict):
            self._client_last_local_input = dict(local_input)

        self.water.update(dt)
        # Advance tile crumbling/warning animations locally so they are smooth
        # between host snapshots without running host-only random tile selection.
        self.tile_manager.advance_visuals(dt)
        self.hazard_manager.advance_visuals(dt)
        self.orb_manager.advance_visuals(dt)
        if self.pacman_enemy_manager:
            self.pacman_enemy_manager.advance_visuals(dt)
        if self.elimination_screen:
            self.elimination_screen.update(dt)

        local_player = self._local_network_player()
        predicted_local = False
        if (
            self._client_prediction_enabled
            and isinstance(local_input, dict)
            and local_player is not None
            and local_player not in self.eliminated_players
            and not bool(self.paused)
            and not bool(self.game_over)
        ):
            # Client-side prediction: run local movement immediately for responsive
            # controls, then reconcile toward host snapshots as they arrive.
            local_player.update_from_input_state(
                dt,
                local_input,
                self.walkable_mask,
                self.walkable_bounds,
            )
            if local_player.power:
                local_player.power.update(dt, local_player)
            predicted_local = True

        extrapolation_dt = min(max(0.0, float(dt)), self._client_remote_extrapolation_cap)
        for player in self.players:
            player._eliminated = player in self.eliminated_players

            if player is not local_player and not player._eliminated:
                # Lightweight dead-reckoning between snapshots reduces visible
                # stepping when packets arrive unevenly.
                if not player.falling and not player.drowning and str(getattr(player, "state", "")) != "death":
                    delta = pygame.Vector2(player.velocity) * extrapolation_dt
                    max_step = 18.0
                    if delta.length_squared() > max_step * max_step:
                        delta.scale_to_length(max_step)
                    if delta.length_squared() > 0.0:
                        if self.walkable_mask is not None and hasattr(player, "_attempt_move"):
                            player._attempt_move(delta, self.walkable_mask)
                        else:
                            player.position += delta
                        player.rect.center = (round(player.position.x), round(player.position.y))

            if predicted_local and player is local_player:
                continue
            player.current_animation.update(dt)

    def _process_network_messages(self):
        latest_snapshot = None
        latest_world_snapshot = None
        latest_world_dynamic_snapshot = None
        latest_match_result = None
        saw_disconnect = False
        message_count = 0
        
        # Diagnostic: Track message arrival
        debug_msg_types = []
        
        for message in self.network.get_messages():
            message_count += 1
            message_type = message.get("type")
            debug_msg_types.append(message_type)
            
            if message_type == "disconnect":
                saw_disconnect = True
                continue
            if message_type == "pause_state":
                self.paused = bool(message.get("paused", False))
            elif self.is_network_host and message_type == "pause_toggle_request":
                self._toggle_pause()
            elif self.is_network_host and message_type == "restart_request":
                self._restart_network_round(reset_match=bool(message.get("reset_match", False)))
            elif self.is_network_host and message_type == "input_state":
                self._remote_input_state = self._sanitize_network_input(message.get("input"))
            elif self.is_network_host and message_type == "power_use_request":
                self._pending_remote_power_uses = min(8, self._pending_remote_power_uses + 1)
            elif (not self.is_network_host) and message_type == "snapshot":
                latest_snapshot = message
            elif (not self.is_network_host) and message_type == "world_snapshot":
                latest_world_snapshot = message
            elif (not self.is_network_host) and message_type == "world_dynamic_snapshot":
                latest_world_dynamic_snapshot = message
            elif (not self.is_network_host) and message_type == "match_result":
                latest_match_result = message
        
        # Diagnostic: Log message batch info
        if message_count > 0:
            try:
                print(f"[DIAG] ProcessMessages: got {message_count} messages, types={set(debug_msg_types)}, snap={latest_snapshot is not None}, world_snap={latest_world_snapshot is not None}", flush=True)
            except Exception:
                pass

        if latest_snapshot is not None:
            self._apply_network_snapshot(latest_snapshot)
        if latest_world_snapshot is not None:
            self._apply_network_world_snapshot(latest_world_snapshot)
        if latest_world_dynamic_snapshot is not None:
            self._apply_network_world_snapshot(latest_world_dynamic_snapshot)
        if latest_match_result is not None:
            self._apply_network_match_result(latest_match_result)
        if saw_disconnect:
            now = time.time()
            if self._network_disconnect_started_at is None:
                self._network_disconnect_started_at = now
            try:
                print("[DEBUG] network disconnect received; entering reconnect grace", flush=True)
            except Exception:
                pass
            return

    def _build_local_input_state(self, keys) -> dict:
        player = self._local_network_player()
        controls = getattr(player, "controls", {}) if player else {}
        return {
            "up": bool(keys[controls.get("up", pygame.K_w)]),
            "down": bool(keys[controls.get("down", pygame.K_s)]),
            "left": bool(keys[controls.get("left", pygame.K_a)]),
            "right": bool(keys[controls.get("right", pygame.K_d)]),
            "jump": bool(keys[controls.get("jump", pygame.K_SPACE)]),
            "power_pressed": bool(self._pending_power_press),
        }

    def _empty_network_input_state(self) -> dict:
        return {
            "up": False,
            "down": False,
            "left": False,
            "right": False,
            "jump": False,
            "power_pressed": False,
        }

    def _sanitize_network_input(self, payload) -> dict:
        clean = self._empty_network_input_state()
        if not isinstance(payload, dict):
            return clean
        for key in clean:
            clean[key] = bool(payload.get(key, False))
        return clean

    def _local_network_player(self):
        if not self.is_network_game:
            return None
        if 0 <= self.local_player_index < len(self.players):
            return self.players[self.local_player_index]
        return None

    def _send_pause_state(self):
        if self.is_network_game and self.is_network_host and self.network and self.network.connected:
            self.network.send_message("pause_state", paused=bool(self.paused))

    def _toggle_pause(self):
        if self.is_network_game:
            if self.is_network_host:
                self.paused = not bool(self.paused)
                self._send_pause_state()
            elif self.network and self.network.connected:
                self.network.send_message("pause_toggle_request")
            return

        self.paused = not bool(self.paused)

    def _blend_client_player_snapshot(self, player, player_state: dict) -> dict:
        """Smooth host snapshots on the client to reduce visible jitter."""
        if self.is_network_host or not isinstance(player_state, dict):
            return player_state

        try:
            target = pygame.Vector2(
                float(player_state.get("x", player.position.x)),
                float(player_state.get("y", player.position.y)),
            )
        except (TypeError, ValueError):
            return player_state

        # Snap immediately during major state transitions to avoid desync artifacts.
        if bool(player_state.get("falling", False)) != bool(getattr(player, "falling", False)):
            return player_state
        if bool(player_state.get("drowning", False)) != bool(getattr(player, "drowning", False)):
            return player_state
        if bool(player_state.get("eliminated", False)) != bool(getattr(player, "_eliminated", False)):
            return player_state
        if str(player_state.get("state", "")) == "death":
            return player_state

        current = pygame.Vector2(player.position)
        distance = current.distance_to(target)
        if distance > self._client_snap_distance:
            return player_state

        local_player = self._local_network_player()
        is_local_player = player is local_player
        local_input = self._client_last_local_input if is_local_player else None
        local_move_intent = bool(
            isinstance(local_input, dict)
            and (
                local_input.get("up")
                or local_input.get("down")
                or local_input.get("left")
                or local_input.get("right")
                or local_input.get("jump")
            )
        )

        if is_local_player and local_move_intent and distance <= self._client_local_reconcile_deadzone:
            blended = dict(player_state)
            blended["x"] = current.x
            blended["y"] = current.y
            return blended

        base_blend = (
            self._client_local_position_blend
            if is_local_player
            else self._client_position_blend
        )
        if is_local_player and local_move_intent:
            base_blend *= 0.75
        expected_interval = max(1e-4, float(self._snapshot_interval))
        gap_ratio = max(0.7, min(1.8, float(self._client_snapshot_gap) / expected_interval))
        blend = min(0.9, base_blend * gap_ratio)
        if distance > 72.0:
            blend = min(0.95, blend + 0.12)
        if distance < 3.0 and not (is_local_player and local_move_intent):
            blend = 1.0
        blended = dict(player_state)
        blended["x"] = current.x + (target.x - current.x) * blend
        blended["y"] = current.y + (target.y - current.y) * blend
        return blended

    def _build_network_snapshot(self) -> dict:
        end_state = None
        if self.game_over_state == "victory" and self.victory_screen:
            end_state = {
                "type": "victory",
                "winner_name": self.victory_screen.player_name,
                "winner_character": self.victory_screen.character_name,
                "survival_time": float(self.victory_screen.survival_time),
            }
        elif self.game_over_state == "elimination" and self.elimination_screen:
            end_state = {
                "type": "elimination",
                "player_name": self.elimination_screen.player_name,
                "character_name": self.elimination_screen.character_name,
                "survival_time": float(self.elimination_screen.survival_time),
                "reason": self.elimination_screen.reason,
            }

        snapshot = {
            "time_since_start": float(self._time_since_start),
            "round_seq": int(self._network_round_seq),
            "paused": bool(self.paused),
            "game_over": bool(self.game_over),
            "target_score": int(self.target_score),
            "round_wins": [int(value) for value in self.round_wins],
            "match_complete": bool(self._match_complete),
            "end_state": end_state,
            "players": [
                {
                    "player": player.snapshot_state(),
                    "power": snapshot_power_state(player.power),
                }
                for player in self.players
            ],
            "hud": self.hud.snapshot_state(),
        }
        return snapshot

    def _build_network_world_snapshot(self) -> dict:
        return {
            "time_since_start": float(self._time_since_start),
            "round_seq": int(self._network_round_seq),
            "tiles": self.tile_manager.snapshot_state(),
        }

    def _build_network_dynamic_world_snapshot(self) -> dict:
        return {
            "time_since_start": float(self._time_since_start),
            "round_seq": int(self._network_round_seq),
            "hazards": self.hazard_manager.snapshot_state(),
            "orbs": self.orb_manager.snapshot_state(),
            "pacman_enemies": (
                self.pacman_enemy_manager.snapshot_state()
                if self.pacman_enemy_manager
                else None
            ),
        }

    @staticmethod
    def _parse_round_seq(value: Any, fallback: int) -> int:
        try:
            seq = int(value)
        except (TypeError, ValueError):
            seq = int(fallback)
        return max(0, seq)

    def _reset_client_round_world_state(self) -> None:
        """Reset client-side world objects when host advances to a new round."""
        self.game_over = False
        self.elimination_screen = None
        self.victory_screen = None
        self.game_over_state = None
        self._round_transition_seen = False
        self._round_restart_timer = 0.0
        self._last_client_world_snapshot_time = -1.0
        self._last_client_world_dynamic_snapshot_time = -1.0
        self._last_client_tile_snapshot_time = -1.0
        self._last_client_hazard_snapshot_time = -1.0
        self._last_client_orb_snapshot_time = -1.0
        self._last_client_pacman_snapshot_time = -1.0

        self.tile_manager.reset()
        self.walkable_mask = self.original_walkable_mask.copy() if self.original_walkable_mask else None
        self.hazard_manager.reset()
        self.orb_manager.reset()
        if self.pacman_enemy_manager:
            self.pacman_enemy_manager.reset()

        self.eliminated_players.clear()
        for player in self.players:
            player._eliminated = False

    def _apply_network_snapshot(self, snapshot):
        if not isinstance(snapshot, dict):
            return

        # Diagnostic: snapshot receipt timing
        snapshot_time = float(snapshot.get("time_since_start", -1.0))
        try:
            print(f"[SNAPSHOT] Received snap: round_seq={snapshot.get('round_seq')}, time={snapshot_time:.3f}s, players_count={len(snapshot.get('players', []))}, has_hazards={bool(snapshot.get('hazards'))}", flush=True)
        except Exception:
            pass

        incoming_round_seq = self._parse_round_seq(
            snapshot.get("round_seq", self._last_client_snapshot_round_seq),
            self._last_client_snapshot_round_seq if self._last_client_snapshot_round_seq >= 0 else self._network_round_seq,
        )
        if self._last_client_snapshot_round_seq >= 0 and incoming_round_seq < self._last_client_snapshot_round_seq:
            return
        if incoming_round_seq > self._last_client_snapshot_round_seq:
            self._network_round_seq = incoming_round_seq
            self._last_client_snapshot_round_seq = incoming_round_seq
            if self._last_client_world_snapshot_round_seq < incoming_round_seq:
                self._last_client_world_snapshot_round_seq = incoming_round_seq
            self._last_client_snapshot_time = -1.0
            self._reset_client_round_world_state()

        previous_time = self._last_client_snapshot_time
        incoming_time = float(snapshot.get("time_since_start", self._time_since_start))
        if incoming_time + 1e-6 < self._last_client_snapshot_time:
            return
        if previous_time >= 0.0:
            gap = incoming_time - previous_time
            if gap > 0.0:
                self._client_snapshot_gap = min(0.5, gap)
        self._last_client_snapshot_time = incoming_time
        self._time_since_start = incoming_time
        self.paused = bool(snapshot.get("paused", self.paused))
        self.target_score = max(1, int(snapshot.get("target_score", self.target_score)))
        incoming_round_wins = snapshot.get("round_wins", self.round_wins)
        if isinstance(incoming_round_wins, list):
            self.round_wins = [int(max(0, value)) for value in incoming_round_wins]
        if len(self.round_wins) < len(self.players):
            self.round_wins.extend([0] * (len(self.players) - len(self.round_wins)))
        elif len(self.round_wins) > len(self.players):
            self.round_wins = self.round_wins[: len(self.players)]
        self._match_complete = bool(snapshot.get("match_complete", self._match_complete))
        self.hud.apply_snapshot(snapshot.get("hud"))
        self.hud.set_round_scoreboard(self.round_wins, self.target_score)

        # Backward compatibility path if an older host still sends full snapshots.
        if any(key in snapshot for key in ("tiles", "hazards", "orbs", "pacman_enemies")):
            self._apply_network_world_snapshot(snapshot)

        self.eliminated_players.clear()
        self.victory_screen = None
        self.elimination_screen = None
        self.game_over_state = None
        for idx, entry in enumerate(snapshot.get("players", []) or []):
            if idx >= len(self.players) or not isinstance(entry, dict):
                continue
            player_state = entry.get("player") or {}
            player = self.players[idx]
            blended_state = self._blend_client_player_snapshot(player, player_state)
            player.apply_snapshot_state(blended_state)
            apply_power_state(player.power, entry.get("power"))
            if player_state.get("eliminated"):
                self.eliminated_players.append(player)

        next_game_over = bool(snapshot.get("game_over", False))
        if next_game_over and not self.game_over:
            end_state = snapshot.get("end_state") or {}
            if isinstance(end_state, dict) and end_state.get("type") == "victory":
                winner_name = str(end_state.get("winner_name", self.player_name))
                char_name = str(end_state.get("winner_character", "Caveman"))
                self._trigger_victory(winner_name, char_name)
            else:
                self._trigger_game_over()
        elif not next_game_over and self.game_over:
            self.game_over = False
            self.elimination_screen = None
            self.victory_screen = None
            self.game_over_state = None

    def _apply_network_world_snapshot(self, snapshot):
        if not isinstance(snapshot, dict):
            return

        incoming_round_seq = self._parse_round_seq(
            snapshot.get("round_seq", self._last_client_world_snapshot_round_seq),
            self._last_client_world_snapshot_round_seq if self._last_client_world_snapshot_round_seq >= 0 else self._network_round_seq,
        )
        if self._last_client_world_snapshot_round_seq >= 0 and incoming_round_seq < self._last_client_world_snapshot_round_seq:
            return
        if incoming_round_seq > self._last_client_world_snapshot_round_seq:
            self._network_round_seq = incoming_round_seq
            self._last_client_world_snapshot_round_seq = incoming_round_seq
            self._reset_client_round_world_state()

        incoming_time = float(snapshot.get("time_since_start", self._time_since_start))
        epsilon = 1e-6
        applied_any = False

        if "tiles" in snapshot and incoming_time + epsilon >= self._last_client_tile_snapshot_time:
            self.tile_manager.apply_snapshot(snapshot.get("tiles"))
            self.walkable_mask = self.tile_manager.get_updated_walkable_mask(self.original_walkable_mask)
            self._last_client_tile_snapshot_time = incoming_time
            applied_any = True
        if "hazards" in snapshot and incoming_time + epsilon >= self._last_client_hazard_snapshot_time:
            self.hazard_manager.apply_snapshot(snapshot.get("hazards"))
            self._last_client_hazard_snapshot_time = incoming_time
            applied_any = True
        if "orbs" in snapshot and incoming_time + epsilon >= self._last_client_orb_snapshot_time:
            self.orb_manager.apply_snapshot(snapshot.get("orbs"))
            self._last_client_orb_snapshot_time = incoming_time
            applied_any = True
        if (
            "pacman_enemies" in snapshot
            and incoming_time + epsilon >= self._last_client_pacman_snapshot_time
        ):
            if self.pacman_enemy_manager is None:
                enemy_states = snapshot.get("pacman_enemies", {}).get("enemies", []) or []
                spawn_positions = [
                    (int(round(state.get("x", PLAYER_START_POS[0]))), int(round(state.get("y", PLAYER_START_POS[1]))))
                    for state in enemy_states
                    if isinstance(state, dict)
                ] or [PLAYER_START_POS]
                self.pacman_enemy_manager = PacmanEnemyManager(spawn_positions)
            self.pacman_enemy_manager.apply_snapshot(snapshot.get("pacman_enemies"))
            self._last_client_pacman_snapshot_time = incoming_time
            applied_any = True

        if applied_any:
            self._last_client_world_snapshot_time = max(
                self._last_client_world_snapshot_time,
                incoming_time,
            )
            if "tiles" not in snapshot:
                self._last_client_world_dynamic_snapshot_time = max(
                    self._last_client_world_dynamic_snapshot_time,
                    incoming_time,
                )

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

        # Draw pacman-style enemies before the player front layer
        if self.pacman_enemy_manager:
            self.pacman_enemy_manager.draw(self.screen)

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
        self.hud.draw(
            self.screen,
            self.players,
            is_muted=self.audio.is_muted,
            volume=self.audio.get_volume(),
            is_paused=bool(self.paused),
        )

        # Draw elimination screen if game over
        if self.victory_screen:
            self.victory_screen.draw(self.screen)
        elif self.elimination_screen:
            self.elimination_screen.draw(self.screen)
            
        if getattr(self, "paused", False):
            s_overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            s_overlay.fill((0, 0, 0, 128))
            self.screen.blit(s_overlay, (0, 0))
            
            # Using default pygame font since settings.py isn't guaranteed to have standard sizes loaded here
            font = pygame.font.Font(None, 74)
            text = font.render(f"PAUSED", True, (255, 255, 255))
            text_rect = text.get_rect(center=(WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2))
            
            font_small = pygame.font.Font(None, 36)
            sub_text = font_small.render(f"Press TAB to Resume", True, (200, 200, 220))
            sub_rect = sub_text.get_rect(center=(WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2 + 50))
            
            menu_text = font_small.render(f"To go to Main Menu, press Left Ctrl", True, (150, 150, 180))
            menu_rect = menu_text.get_rect(center=(WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2 + 85))
            
            self.screen.blit(text, text_rect)
            self.screen.blit(sub_text, sub_rect)
            self.screen.blit(menu_text, menu_rect)

        reserved: list[pygame.Rect] = []
        for rect in (
            self.hud.pause_rect,
            self.hud.mute_rect,
            self.hud.volume_rect,
            self.hud.timer_rect,
            self.hud.alive_rect,
        ):
            if isinstance(rect, pygame.Rect):
                reserved.append(rect)
        for rect in self.hud.player_card_rects:
            if isinstance(rect, pygame.Rect):
                reserved.append(rect)

        draw_online_status_badge(
            self.screen,
            reserved_rects=reserved,
            preferred_corners=("bottom-right", "top-right", "bottom-left", "top-left"),
        )

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
                fallback = self._find_valid_fallback(player, occupied, walkable_center)
                if fallback is not None:
                    desired = fallback
            if desired in occupied or not self._is_spawn_position_valid(player, desired):
                continue
            self._apply_spawn_position(player, desired)
            occupied.add(desired)
        self._align_ai_spawn_with_human()
        self._spawn_adjusted = True

    def _is_spawn_position_valid(self, player, position: tuple[int, int]) -> bool:
        return player._is_over_platform(pygame.Vector2(position), self.walkable_mask)

    def _is_respawn_zone_safe(
        self,
        position: tuple[int, int],
        *,
        hazard_radius: float = 48.0,
        enemy_distance: float = 150.0,
    ) -> bool:
        if self.hazard_manager and not self.hazard_manager.is_position_safe(position, radius=hazard_radius):
            return False

        if self.pacman_enemy_manager:
            pos = pygame.Vector2(position)
            for enemy in self.pacman_enemy_manager.enemies:
                enemy_pos = pygame.Vector2(getattr(enemy, "position", enemy.rect.center))
                if pos.distance_to(enemy_pos) < enemy_distance:
                    return False

        return True

    def _find_valid_fallback(
        self,
        player,
        occupied: set[tuple[int, int]],
        origin: pygame.Vector2,
        *,
        ignore_occupied: bool = False,
        require_safe_zone: bool = False,
        hazard_radius: float = 48.0,
        enemy_distance: float = 150.0,
    ) -> tuple[int, int] | None:
        if not self.walkable_mask:
            return None

        step_radius = 20
        max_radius = 400
        angle_step = 15
        for radius in range(0, max_radius + step_radius, step_radius):
            for angle_deg in range(0, 360, angle_step):
                angle_rad = math.radians(angle_deg)
                offset = pygame.Vector2(math.cos(angle_rad), math.sin(angle_rad)) * radius
                candidate = (int(round(origin.x + offset.x)), int(round(origin.y + offset.y)))
                if (not ignore_occupied) and candidate in occupied:
                    continue
                if self._is_spawn_position_valid(player, candidate):
                    if require_safe_zone and not self._is_respawn_zone_safe(
                        candidate,
                        hazard_radius=hazard_radius,
                        enemy_distance=enemy_distance,
                    ):
                        continue
                    return candidate

        origin_candidate = (int(round(origin.x)), int(round(origin.y)))
        if ((ignore_occupied or origin_candidate not in occupied)
                and self._is_spawn_position_valid(player, origin_candidate)):
            if require_safe_zone and not self._is_respawn_zone_safe(
                origin_candidate,
                hazard_radius=hazard_radius,
                enemy_distance=enemy_distance,
            ):
                return None
            return origin_candidate
        return None

    def _restore_nearest_platform_tile(self, origin: pygame.Vector2) -> bool:
        """Emergency fallback: restore a nearby missing tile so respawn has ground."""
        tiles = getattr(self.tile_manager, "tiles", None)
        if not isinstance(tiles, dict) or not tiles:
            return False

        best_tile = None
        best_dist_sq = float("inf")
        origin_x = float(origin.x)
        origin_y = float(origin.y)
        for tile in tiles.values():
            if getattr(tile, "state", TileState.NORMAL) == TileState.NORMAL:
                continue

            center_x = float(tile.pixel_x + tile.tile_width / 2)
            center_y = float(tile.pixel_y + tile.tile_height / 2)
            dist_sq = (center_x - origin_x) ** 2 + (center_y - origin_y) ** 2
            if dist_sq < best_dist_sq:
                best_dist_sq = dist_sq
                best_tile = tile

        if best_tile is None:
            return False

        best_tile.reset()
        self.walkable_mask = self.tile_manager.get_updated_walkable_mask(self.original_walkable_mask)
        return bool(self.walkable_mask)

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
        if not self.walkable_mask and self.original_walkable_mask:
            self.walkable_mask = self.tile_manager.get_updated_walkable_mask(self.original_walkable_mask)
        if not self.walkable_mask:
            return False

        occupied = {
            (int(round(p.position.x)), int(round(p.position.y)))
            for p in self.players
            if p is not player and p not in self.eliminated_players
        }

        walkable_center = self._walkable_center()
        safe_position = self._find_valid_fallback(
            player,
            occupied,
            walkable_center,
            require_safe_zone=True,
            hazard_radius=52.0,
            enemy_distance=170.0,
        )
        if safe_position is None:
            safe_position = self._find_valid_fallback(
                player,
                occupied,
                walkable_center,
                ignore_occupied=True,
                require_safe_zone=True,
                hazard_radius=44.0,
                enemy_distance=130.0,
            )
        if safe_position is None and self._restore_nearest_platform_tile(walkable_center):
            safe_position = self._find_valid_fallback(
                player,
                occupied,
                walkable_center,
                ignore_occupied=True,
                require_safe_zone=True,
                hazard_radius=40.0,
                enemy_distance=120.0,
            )
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
        if hasattr(player, "_death_fade_alpha"):
            player._death_fade_alpha = 255
        if hasattr(player, "_set_state"):
            player._set_state("idle", player.facing)

        if self.is_network_game and self.is_network_host and self.network and self.network.connected:
            self.network.send_message("snapshot", state=self._build_network_snapshot())
            self.network.send_message(
                "world_dynamic_snapshot",
                state=self._build_network_dynamic_world_snapshot(),
            )
            self.network.send_message("world_snapshot", state=self._build_network_world_snapshot())
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

    def _check_life_orb_collection(self, player):
        """Check if player can collect a LIFE orb before elimination."""
        # Check if player is about to be eliminated and can collect a LIFE orb
        for orb in self.orb_manager.orbs:
            if not orb.active:
                continue
            if orb.orb_type.value == "life" and orb.check_collection(player):
                orb.collect()
                from orbs import apply_orb_effect
                msg = apply_orb_effect(orb.orb_type, player, self)
                self.orb_manager._notification = msg
                self.orb_manager._notification_timer = 2.5
                print(f"Player collected LIFE orb before elimination!")
                break

    def _eliminate_player(self, player, reason: str):
        """Mark a player as eliminated."""
        if self._can_block_elimination(player, reason):
            print(f"Elimination blocked by shield/immunity (Reason: {reason})")
            return
        # Check if player has an extra life to revive
        if hasattr(player, 'has_extra_life') and player.has_extra_life():
            if player.use_life():
                # Remove from eliminated list if they were in it
                if player in self.eliminated_players:
                    self.eliminated_players.remove(player)
                # Reset eliminated flag
                player._eliminated = False
                # Revive the player at a safe position
                if self._rescue_player_to_safe_tile(player):
                    print(f"Player revived with extra life! (Reason: {reason})")
                    return
                print("Extra life consumed but no safe platform tile was found; eliminating player.")
        if player not in self.eliminated_players:
            self.eliminated_players.append(player)
            player._eliminated = True
            print(f"Player eliminated: {reason}")
            try:
                eliminated_index = self.players.index(player)
            except ValueError:
                eliminated_index = -1
            if 0 <= eliminated_index < len(self._match_player_stats):
                self._match_player_stats[eliminated_index]["deaths"] += 1
                self._match_player_stats[eliminated_index]["damage_taken"] += 100
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

    def _elimination_animations_finished(self) -> bool:
        """Return True when all eliminated players have fully finished death visuals."""
        for player in self.eliminated_players:
            if getattr(player, "state", "") != "death":
                return False

            animation = getattr(player, "current_animation", None)
            if animation is not None and not bool(getattr(animation, "finished", False)):
                return False

            # Keep end-of-round/game UI hidden until the death fade has finished too.
            if int(getattr(player, "_death_fade_alpha", 255)) > 0:
                return False

            if bool(getattr(player, "drowning", False)) and not bool(
                getattr(player, "drown_animation_done", False)
            ):
                return False

        return True

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

    def _can_use_end_of_match_actions(self) -> bool:
        """Allow restart/menu shortcuts only on final match end screens."""
        return bool(self._match_complete or len(self.players) <= 1)

    def _trigger_game_over(self):
        """Trigger game over state."""
        self._trigger_elimination()

    def _trigger_elimination(self):
        """Trigger the elimination end screen."""
        if not self.game_over:
            self.game_over = True
            self.game_over_state = "elimination"
            self._match_complete = False
            self._round_restart_timer = 0.0
            self.victory_screen = None
            
            char_name = getattr(self.player, "character_name", "Caveman") if hasattr(self, "player") and self.player else "Caveman"
            allow_actions = self._can_use_end_of_match_actions()
            status_text = None if allow_actions else "Next round starts automatically..."
            
            self.elimination_screen = EliminationScreen(
                self.player_name,
                self.hud.survival_time,
                "eliminated",
                char_name,
                allow_actions=allow_actions,
                status_message=status_text,
            )
            self.elimination_screen.show()
            if self.is_network_game and self.is_network_host and self.network and self.network.connected:
                self.network.send_message("snapshot", state=self._build_network_snapshot())

    def _trigger_victory(self, winner_name: str, character_name: str = "Caveman"):
        """Trigger the victory end screen."""
        if not self.game_over:
            self.game_over = True
            self.game_over_state = "victory"
            self._round_restart_timer = 0.0
            self.elimination_screen = None
            allow_actions = self._can_use_end_of_match_actions()
            status_text = None if allow_actions else "Next round starts automatically..."
            self.victory_screen = VictoryScreen(
                winner_name,
                self.hud.survival_time,
                character_name,
                allow_actions=allow_actions,
                status_message=status_text,
            )
            self.victory_screen.show()
            if self.is_network_game and self.is_network_host and self.network and self.network.connected:
                self.network.send_message("snapshot", state=self._build_network_snapshot())

    def _handle_round_victory(self, winner_index: int, winner_label: str):
        """Count round results and show RR/summary only at full match completion."""
        if not self.players:
            return

        winner_index = max(0, min(len(self.players) - 1, int(winner_index)))
        if len(self.round_wins) != len(self.players):
            self.round_wins = [0 for _ in self.players]

        self.round_wins[winner_index] += 1
        self._register_round_stats(winner_index, is_draw=False)
        self.hud.set_round_scoreboard(self.round_wins, self.target_score)
        self._round_restart_timer = 0.0
        self._match_complete = self.round_wins[winner_index] >= self.target_score

        if not self._match_complete:
            if self.is_network_game:
                if self.is_network_host:
                    self._restart_network_round(reset_match=False)
            else:
                self._restart_game(reset_match=False)
            return

        mvp_index = self._compute_mvp_index()
        match_result = self._build_network_match_result(
            winner_index=winner_index,
            mvp_index=mvp_index,
            is_draw=False,
        )
        if self.is_network_game and self.is_network_host and self.network and self.network.connected:
            # Send authoritative final result so the joining client applies the
            # same RR/stats delta to their own local account data.
            self.network.send_message("snapshot", state=self._build_network_snapshot())
            self.network.send_message(
                "match_result",
                state=match_result,
            )

        payload_winner = match_result.get("winner_index", winner_index)
        try:
            payload_winner_index = int(payload_winner)
        except (TypeError, ValueError):
            payload_winner_index = winner_index
        if payload_winner_index < 0 or payload_winner_index >= len(self.players):
            payload_winner_index = None

        payload_mvp = match_result.get("mvp_index", mvp_index)
        try:
            payload_mvp_index = int(payload_mvp)
        except (TypeError, ValueError):
            payload_mvp_index = mvp_index
        if payload_mvp_index < 0 or payload_mvp_index >= len(self.players):
            payload_mvp_index = self._compute_mvp_index()

        payload_is_draw = bool(match_result.get("is_draw", False))
        payload_ranked_mode = (
            match_result.get("ranked_mode")
            if isinstance(match_result.get("ranked_mode"), bool)
            else None
        )
        if payload_is_draw:
            payload_winner_label = "Draw"
        elif payload_winner_index is not None and payload_winner_index < len(self._match_player_stats):
            payload_winner_label = str(
                self._match_player_stats[payload_winner_index].get(
                    "username",
                    self._resolve_player_label(payload_winner_index),
                )
            )
        else:
            payload_winner_label = winner_label

        action = self._run_round_transition(
            payload_winner_index,
            payload_winner_label,
            is_draw=payload_is_draw,
            mvp_index=payload_mvp_index,
            ranked_mode_override=payload_ranked_mode,
        )
        if action == "quit":
            self.running = False
            return
        if action == "menu":
            if self.is_network_game and self.network and self.network.connected:
                self.network.send_message("disconnect")
            self.return_to_main_menu = True
            self.running = False
            return

        self.return_to_main_menu = True
        self.running = False

    def _handle_round_draw(self) -> None:
        """Handle a round where all players are eliminated with no winner."""
        if not self.players:
            return

        self._register_round_stats(None, is_draw=True)
        self.hud.set_round_scoreboard(self.round_wins, self.target_score)
        self._round_restart_timer = 0.0
        self._match_complete = False

        if self.is_network_game:
            if self.is_network_host:
                self._restart_network_round(reset_match=False)
        else:
            self._restart_game(reset_match=False)

    def _resolve_player_label(self, index: int) -> str:
        if 0 <= index < len(self.network_player_names):
            label = self.network_player_names[index].strip()
            if label:
                return label

        if self.account_username and index == (self.local_player_index if self.is_network_game else 0):
            return self.account_username

        player = self.players[index] if 0 <= index < len(self.players) else None
        if player is not None and getattr(player, "is_ai", False):
            return f"AI {index + 1}"

        return f"Player {index + 1}"

    def _new_match_stat_row(self, index: int) -> dict:
        player = self.players[index] if 0 <= index < len(self.players) else None
        return {
            "username": self._resolve_player_label(index),
            "character": str(getattr(player, "character_name", f"Player {index + 1}")),
            "rounds_played": 0,
            "rounds_won": 0,
            "eliminations": 0,
            "deaths": 0,
            "damage_dealt": 0,
            "damage_taken": 0,
            "survival_time": 0.0,
        }

    def _register_round_stats(self, winner_index: int | None, is_draw: bool = False) -> None:
        for idx, row in enumerate(self._match_player_stats):
            row["character"] = str(getattr(self.players[idx], "character_name", row.get("character", "")))
            row["rounds_played"] += 1

            if not is_draw and winner_index is not None and idx == winner_index:
                row["rounds_won"] += 1
                row["eliminations"] += max(0, len(self.players) - 1)
                row["damage_dealt"] += 180
            elif is_draw:
                row["damage_dealt"] += 60
            else:
                # Non-winners still tend to deal some incidental damage during the round.
                row["damage_dealt"] += 40

            if self.players[idx] in self.eliminated_players:
                row["damage_taken"] += 30

    def _compute_mvp_index(self) -> int:
        if not self._match_player_stats:
            return 0

        best_index = 0
        best_score = -10**9
        for idx, row in enumerate(self._match_player_stats):
            score = (
                int(row.get("rounds_won", 0)) * 120
                + int(row.get("eliminations", 0)) * 36
                + int(row.get("damage_dealt", 0)) * 0.12
                + float(row.get("survival_time", 0.0)) * 0.45
                - int(row.get("deaths", 0)) * 28
            )
            if score > best_score:
                best_score = score
                best_index = idx
        return best_index

    def _local_account_index(self) -> int | None:
        if self.is_network_game:
            if 0 <= self.local_player_index < len(self.players):
                return self.local_player_index
            return None
        if self.players:
            return 0
        return None

    def _is_ranked_mode(self) -> bool:
        if self._ranked_override is not None:
            return bool(self._ranked_override)
        # Default behavior: LAN/online matches are ranked, campaign/local multiplayer are unranked.
        return self.game_mode == MODE_ONLINE_MULTIPLAYER

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _share(self, value: float, total: float, neutral: float = 0.5) -> float:
        if total <= 0:
            return float(neutral)
        return self._clamp01(float(value) / float(total))

    def _match_performance_score(
        self,
        local_index: int,
        winner_index: int | None,
        mvp_index: int,
        is_draw: bool = False,
    ) -> float:
        if local_index < 0 or local_index >= len(self._match_player_stats):
            return 0.5

        row = self._match_player_stats[local_index]
        total_rounds_won = sum(max(0, int(r.get("rounds_won", 0))) for r in self._match_player_stats)
        total_eliminations = sum(max(0, int(r.get("eliminations", 0))) for r in self._match_player_stats)
        total_damage_dealt = sum(max(0, int(r.get("damage_dealt", 0))) for r in self._match_player_stats)
        total_damage_taken = sum(max(0, int(r.get("damage_taken", 0))) for r in self._match_player_stats)
        total_survival = sum(max(0.0, float(r.get("survival_time", 0.0))) for r in self._match_player_stats)
        total_deaths = sum(max(0, int(r.get("deaths", 0))) for r in self._match_player_stats)

        rounds_share = self._share(max(0, int(row.get("rounds_won", 0))), total_rounds_won)
        elimination_share = self._share(max(0, int(row.get("eliminations", 0))), total_eliminations)
        dealt_share = self._share(max(0, int(row.get("damage_dealt", 0))), total_damage_dealt)
        taken_efficiency = 1.0 - self._share(max(0, int(row.get("damage_taken", 0))), total_damage_taken)
        survival_share = self._share(max(0.0, float(row.get("survival_time", 0.0))), total_survival)
        death_efficiency = 1.0 - self._share(max(0, int(row.get("deaths", 0))), total_deaths)

        base_score = (
            0.24 * rounds_share
            + 0.17 * elimination_share
            + 0.17 * dealt_share
            + 0.14 * taken_efficiency
            + 0.14 * survival_share
            + 0.14 * death_efficiency
        )
        win_bonus = 0.12 if (winner_index is not None and local_index == winner_index) else 0.0
        mvp_bonus = 0.08 if local_index == mvp_index else 0.0
        draw_bonus = 0.03 if is_draw else 0.0
        return self._clamp01(base_score + win_bonus + mvp_bonus + draw_bonus)

    def _compute_rr_delta(
        self,
        local_index: int,
        winner_index: int | None,
        mvp_index: int,
        is_draw: bool = False,
        ranked_mode: bool = True,
    ) -> int:
        if not ranked_mode:
            return 0
        if is_draw:
            return 0

        max_gain, max_loss = self._rr_caps_for_target_score(self.target_score)
        score = self._match_performance_score(local_index, winner_index, mvp_index, is_draw=is_draw)
        won_match = winner_index is not None and local_index == winner_index
        if won_match:
            gain = int(round(score * float(max_gain)))
            return max(0, min(max_gain, gain))

        loss = int(round((1.0 - score) * float(max_loss)))
        return -max(0, min(max_loss, loss))

    def _rr_caps_for_target_score(self, target_score: int | None = None) -> tuple[int, int]:
        """Scale RR caps by match length so short matches swing less than long matches."""
        score_to_win = int(self.target_score if target_score is None else target_score)

        min_target = 3
        max_target = 20
        min_win_cap = 12
        max_win_cap = 45
        min_lose_cap = 8
        max_lose_cap = 40

        if max_target <= min_target:
            return max_win_cap, max_lose_cap

        t = (score_to_win - min_target) / float(max_target - min_target)
        t = max(0.0, min(1.0, t))
        win_cap = int(round(min_win_cap + (max_win_cap - min_win_cap) * t))
        lose_cap = int(round(min_lose_cap + (max_lose_cap - min_lose_cap) * t))
        return win_cap, lose_cap

    def _build_network_match_result(
        self,
        winner_index: int | None,
        mvp_index: int,
        is_draw: bool = False,
    ) -> dict:
        self._match_result_serial += 1
        match_stats: list[dict[str, Any]] = []
        for idx in range(len(self.players)):
            row = self._match_player_stats[idx] if idx < len(self._match_player_stats) else self._new_match_stat_row(idx)
            match_stats.append(
                {
                    "username": str(row.get("username", self._resolve_player_label(idx))),
                    "character": str(row.get("character", getattr(self.players[idx], "character_name", "Caveman"))),
                    "rounds_played": int(max(0, row.get("rounds_played", 0))),
                    "rounds_won": int(max(0, row.get("rounds_won", 0))),
                    "eliminations": int(max(0, row.get("eliminations", 0))),
                    "deaths": int(max(0, row.get("deaths", 0))),
                    "damage_dealt": int(max(0, row.get("damage_dealt", 0))),
                    "damage_taken": int(max(0, row.get("damage_taken", 0))),
                    "survival_time": float(max(0.0, row.get("survival_time", 0.0))),
                }
            )

        winner_value = int(winner_index) if winner_index is not None else -1
        result_id = f"match_result_{self._match_result_serial}_{int(self._time_since_start * 1000)}"
        return {
            "result_id": result_id,
            "winner_index": winner_value,
            "mvp_index": int(max(0, mvp_index)),
            "is_draw": bool(is_draw),
            "match_complete": bool(self._match_complete),
            "ranked_mode": bool(self._is_ranked_mode()),
            "target_score": int(self.target_score),
            "round_wins": [int(value) for value in self.round_wins],
            "match_stats": match_stats,
        }

    def _apply_network_match_result(self, state: Any) -> None:
        if self.is_network_host or not isinstance(state, dict):
            return

        raw_result_id = state.get("result_id")
        result_id = str(raw_result_id).strip() if raw_result_id is not None else ""
        if result_id and result_id == self._last_applied_match_result_id:
            return

        ranked_mode_override = state.get("ranked_mode") if isinstance(state.get("ranked_mode"), bool) else None
        is_draw = bool(state.get("is_draw", False))
        self._match_complete = bool(state.get("match_complete", self._match_complete))
        if "target_score" in state:
            try:
                self.target_score = max(1, int(state.get("target_score", self.target_score)))
            except (TypeError, ValueError):
                pass

        incoming_round_wins = state.get("round_wins")
        if isinstance(incoming_round_wins, list):
            self.round_wins = [int(max(0, value)) for value in incoming_round_wins]
            if len(self.round_wins) < len(self.players):
                self.round_wins.extend([0] * (len(self.players) - len(self.round_wins)))
            elif len(self.round_wins) > len(self.players):
                self.round_wins = self.round_wins[: len(self.players)]
            self.hud.set_round_scoreboard(self.round_wins, self.target_score)

        incoming_stats = state.get("match_stats")
        if isinstance(incoming_stats, list) and incoming_stats:
            rebuilt_stats: list[dict[str, Any]] = []
            for idx in range(len(self.players)):
                entry = incoming_stats[idx] if idx < len(incoming_stats) and isinstance(incoming_stats[idx], dict) else {}
                rebuilt_stats.append(
                    {
                        "username": str(entry.get("username", self._resolve_player_label(idx))),
                        "character": str(entry.get("character", getattr(self.players[idx], "character_name", "Caveman"))),
                        "rounds_played": int(max(0, entry.get("rounds_played", 0))),
                        "rounds_won": int(max(0, entry.get("rounds_won", 0))),
                        "eliminations": int(max(0, entry.get("eliminations", 0))),
                        "deaths": int(max(0, entry.get("deaths", 0))),
                        "damage_dealt": int(max(0, entry.get("damage_dealt", 0))),
                        "damage_taken": int(max(0, entry.get("damage_taken", 0))),
                        "survival_time": float(max(0.0, entry.get("survival_time", 0.0))),
                    }
                )
            self._match_player_stats = rebuilt_stats

        raw_winner_index = state.get("winner_index", -1)
        try:
            winner_index = int(raw_winner_index)
        except (TypeError, ValueError):
            winner_index = -1
        if winner_index < 0 or winner_index >= len(self.players):
            winner_index = None

        raw_mvp_index = state.get("mvp_index", 0)
        try:
            mvp_index = int(raw_mvp_index)
        except (TypeError, ValueError):
            mvp_index = 0
        if mvp_index < 0 or mvp_index >= len(self.players):
            mvp_index = 0

        if result_id:
            self._last_applied_match_result_id = result_id
        else:
            self._last_applied_match_result_id = f"legacy_{winner_index}_{mvp_index}_{int(self._time_since_start * 1000)}"

        if is_draw:
            winner_label = "Draw"
        elif winner_index is not None and winner_index < len(self._match_player_stats):
            winner_label = str(
                self._match_player_stats[winner_index].get(
                    "username",
                    self._resolve_player_label(winner_index),
                )
            )
        elif winner_index is not None:
            winner_label = self._resolve_player_label(winner_index)
        else:
            winner_label = self.player_name

        action = self._run_round_transition(
            winner_index,
            winner_label,
            is_draw=is_draw,
            mvp_index=mvp_index,
            ranked_mode_override=ranked_mode_override,
        )
        if action == "quit":
            self.running = False
            return
        if action == "menu":
            if self.is_network_game and self.network and self.network.connected:
                self.network.send_message("disconnect")
            self.return_to_main_menu = True
            self.running = False
            return

        self.return_to_main_menu = True
        self.running = False

    def _apply_local_account_round_result(
        self,
        winner_index: int | None,
        mvp_index: int,
        is_draw: bool = False,
        ranked_mode_override: bool | None = None,
    ) -> tuple[str, int, int, int]:
        local_index = self._local_account_index()
        local_label = self.account_username or self.player_name
        rr_before = int(self._guest_rr)
        rr_after = rr_before
        rr_delta = 0

        if local_index is None:
            return local_label, rr_before, rr_after, rr_delta

        ranked_mode = self._is_ranked_mode() if ranked_mode_override is None else bool(ranked_mode_override)
        rr_delta = self._compute_rr_delta(
            local_index,
            winner_index,
            mvp_index,
            is_draw=is_draw,
            ranked_mode=ranked_mode,
        )

        local_row = self._match_player_stats[local_index] if local_index < len(self._match_player_stats) else {}
        damage_dealt_delta = int(max(0, local_row.get("damage_dealt", 0)))
        damage_taken_delta = int(max(0, local_row.get("damage_taken", 0)))
        eliminations_delta = int(max(0, local_row.get("eliminations", 0)))
        deaths_delta = int(max(0, local_row.get("deaths", 0)))
        rounds_played_delta = int(max(0, local_row.get("rounds_played", 0)))
        rounds_won_delta = int(max(0, local_row.get("rounds_won", 0)))

        did_win_match = bool(self._match_complete and not is_draw and winner_index is not None and local_index == winner_index)
        matches_played_delta = 1 if self._match_complete else 0
        matches_won_delta = 1 if did_win_match else 0
        mvp_delta = 1 if self._match_complete and local_index == mvp_index else 0

        if self.account_service and self.account_username:
            profile_before = self.account_service.get_profile(self.account_username)
            if profile_before is not None:
                rr_before = int(profile_before.rr)

            updated = self.account_service.apply_stat_delta(
                self.account_username,
                rr_delta=rr_delta,
                damage_dealt=damage_dealt_delta,
                damage_taken=damage_taken_delta,
                eliminations=eliminations_delta,
                deaths=deaths_delta,
                rounds_played=rounds_played_delta,
                rounds_won=rounds_won_delta,
                matches_played=matches_played_delta,
                matches_won=matches_won_delta,
                mvp_count=mvp_delta,
                ranked=ranked_mode,
                sync_now=False,
            )
            if updated is not None:
                rr_after = int(updated.rr)
                self._guest_rr = rr_after
            else:
                rr_after = max(0, rr_before + rr_delta) if ranked_mode else rr_before
                self._guest_rr = rr_after
        else:
            rr_before = int(self._guest_rr)
            rr_after = max(0, rr_before + rr_delta) if ranked_mode else rr_before
            self._guest_rr = rr_after

        return local_label, rr_before, rr_after, rr_delta

    def _build_summary_rows(self) -> list[dict]:
        rows: list[dict] = []
        for idx, row in enumerate(self._match_player_stats):
            rows.append(
                {
                    "username": str(row.get("username", self._resolve_player_label(idx))),
                    "character": str(row.get("character", getattr(self.players[idx], "character_name", "Caveman"))),
                    "rounds_won": int(row.get("rounds_won", 0)),
                    "eliminations": int(row.get("eliminations", 0)),
                    "deaths": int(row.get("deaths", 0)),
                    "damage_dealt": int(row.get("damage_dealt", 0)),
                    "damage_taken": int(row.get("damage_taken", 0)),
                }
            )
        return rows

    def _run_round_transition(
        self,
        winner_index: int | None,
        winner_label: str,
        is_draw: bool = False,
        mvp_index: int | None = None,
        ranked_mode_override: bool | None = None,
    ) -> str:
        if mvp_index is None:
            mvp_index = self._compute_mvp_index()
        if self._match_player_stats:
            mvp_index = max(0, min(len(self._match_player_stats) - 1, int(mvp_index)))
            mvp_name = self._match_player_stats[mvp_index]["username"]
        else:
            mvp_name = winner_label

        rr_user, _rr_before, rr_after, _rr_delta = self._apply_local_account_round_result(
            winner_index,
            mvp_index,
            is_draw=is_draw,
            ranked_mode_override=ranked_mode_override,
        )
        ranked_mode = self._is_ranked_mode() if ranked_mode_override is None else bool(ranked_mode_override)
        if ranked_mode:
            rr_start = int(self._match_rr_start)
            rr_screen = RRGainScreen(rr_user, rr_start, rr_after, "RANKED MATCH COMPLETE")
            rr_action = rr_screen.run(self.screen, self.clock)
            if rr_action in {"quit", "menu"}:
                return rr_action

        summary_prefix = "Ranked" if ranked_mode else "Unranked"
        if is_draw:
            summary_title = f"{summary_prefix} Match Draw"
        else:
            summary_title = f"{summary_prefix} Match Winner: {winner_label}"
        summary_screen = MatchSummaryScreen(
            self._build_summary_rows(),
            mvp_name,
            summary_title,
            allow_continue=False,
        )
        return summary_screen.run(self.screen, self.clock)

    def _restart_game(self, reset_match: bool = False):
        """Restart the game."""
        self.game_over = False
        self.paused = False
        self.elimination_screen = None
        self.victory_screen = None
        self.game_over_state = None
        self._match_complete = False
        self._round_transition_seen = False
        self._round_restart_timer = 0.0
        if reset_match or len(self.round_wins) != len(self.players):
            self.round_wins = [0 for _ in self.players]
        if reset_match or len(self._match_player_stats) != len(self.players):
            self._match_player_labels = [self._resolve_player_label(idx) for idx in range(len(self.players))]
            self._match_player_stats = [self._new_match_stat_row(idx) for idx in range(len(self.players))]
        self.eliminated_players.clear()
        self._pending_power_press = False
        self._pending_remote_power_uses = 0
        self._remote_input_state = self._empty_network_input_state()
        self._authoritative_network_inputs = None
        self._snapshot_send_timer = self._snapshot_interval
        self._world_dynamic_snapshot_send_timer = 0.0
        self._world_snapshot_send_timer = 0.0
        self._network_round_seq = max(0, int(self._network_round_seq) + 1)
        self._last_client_snapshot_time = -1.0
        self._last_client_world_snapshot_time = -1.0
        self._last_client_world_dynamic_snapshot_time = -1.0
        self._last_client_tile_snapshot_time = -1.0
        self._last_client_hazard_snapshot_time = -1.0
        self._last_client_orb_snapshot_time = -1.0
        self._last_client_pacman_snapshot_time = -1.0
        self._last_client_snapshot_round_seq = -1
        self._last_client_world_snapshot_round_seq = -1
        self._client_last_local_input = self._empty_network_input_state()
        self._client_snapshot_gap = self._snapshot_interval
        if reset_match:
            self._last_applied_match_result_id = None
        if self.account_service and self.account_username:
            profile = self.account_service.get_profile(self.account_username)
            if profile is not None:
                self._guest_rr = int(profile.rr)
        if reset_match:
            self._match_rr_start = int(self._guest_rr)
        # Reset input rate-limiter so stale state from the previous round does
        # not suppress the first input message of the new round.
        self._last_sent_input = None
        self._input_send_timer = 0.0

        self.tile_manager.reset()
        self.walkable_mask = self.original_walkable_mask.copy() if self.original_walkable_mask else None
        self.hazard_manager.reset()
        self.orb_manager.reset()
        self.hud.reset()
        self._spawn_adjusted = False
        self._time_since_start = 0.0

        if self.pacman_enemy_manager:
            self.pacman_enemy_manager.reset()

        for player in self.players:
            player.reset()
            if player.power:
                player.power.reset()

        self._ensure_players_on_walkable_surface()
        self._force_safe_spawns()
        self._configure_powers_for_players()
        self.hud.set_player_info(self.player_name, len(self.players), len(self.players))
        self.hud.set_round_scoreboard(self.round_wins, self.target_score)

    def _restart_network_round(self, reset_match: bool = False):
        """Host-authoritative restart path for LAN games."""
        self._network_round_seq += 1
        self._restart_game(reset_match=reset_match)
        if self.is_network_game and self.is_network_host and self.network and self.network.connected:
            self._snapshot_send_timer = 0.0
            self._world_dynamic_snapshot_send_timer = 0.0
            self._world_snapshot_send_timer = 0.0
            try:
                print(f"[NETWORK] Advancing to round_seq={self._network_round_seq} reset_match={reset_match}", flush=True)
            except Exception:
                pass
            self.network.send_message("snapshot", state=self._build_network_snapshot())
            self.network.send_message(
                "world_dynamic_snapshot",
                state=self._build_network_dynamic_world_snapshot(),
            )
            self.network.send_message("world_snapshot", state=self._build_network_world_snapshot())

    def _start_network_reconnect_worker(self) -> None:
        if self._network_reconnect_thread and self._network_reconnect_thread.is_alive():
            return

        def worker() -> None:
            attempt = 0
            while self.running and self.is_network_game and self.network and not self.network.connected:
                base_delay = min(4.0, 0.35 * (2 ** attempt))
                jitter = random.uniform(0.0, min(0.75, base_delay * 0.4))
                delay = base_delay + jitter
                try:
                    print(f"[NETWORK] Reconnect worker attempt={attempt + 1} sleep={delay:.2f}s", flush=True)
                except Exception:
                    pass
                time.sleep(delay)
                if not self.running or not self.is_network_game or not self.network or self.network.connected:
                    break
                try:
                    if self.network.reconnect(attempts=1):
                        try:
                            print(f"[NETWORK] Reconnected at time={self._time_since_start:.1f}s", flush=True)
                        except Exception:
                            pass
                        self._network_disconnect_started_at = None
                        self._network_last_reconnect_attempt_at = 0.0
                        return
                except Exception as exc:
                    try:
                        print(f"[NETWORK] Reconnect attempt failed: {exc}", flush=True)
                    except Exception:
                        pass
                attempt += 1

            try:
                print("[NETWORK] Reconnect worker exited", flush=True)
            except Exception:
                pass
            self._network_reconnect_thread = None

    def _force_safe_spawns(self):
        """Clamp every player to a valid walkable tile and clear fall/drown flags."""
        if not self.walkable_mask:
            return
        center = self._walkable_center()
        occupied: set[tuple[int, int]] = set()
        for player in self.players:
            pos_tuple = (int(round(player.position.x)), int(round(player.position.y)))
            if (
                pos_tuple in occupied
                or not self._is_spawn_position_valid(player, pos_tuple)
                or not self._is_respawn_zone_safe(pos_tuple, hazard_radius=44.0, enemy_distance=120.0)
            ):
                safe = self._find_valid_fallback(
                    player,
                    occupied,
                    center,
                    ignore_occupied=True,
                    require_safe_zone=True,
                    hazard_radius=40.0,
                    enemy_distance=120.0,
                )
                if safe is None:
                    safe = self._find_valid_fallback(
                        player,
                        occupied,
                        center,
                        ignore_occupied=True,
                    )
                if safe is not None:
                    self._apply_spawn_position(player, safe)
                    pos_tuple = safe

            occupied.add(pos_tuple)
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
                power = getattr(player, "power", None)
                if power and hasattr(power, "blocks_player_motion") and power.blocks_player_motion():
                    confirm = getattr(power, "confirm_target_selection", None)
                    if callable(confirm) and confirm(self):
                        break
                    break
                if player.try_use_power(self):
                    break

    def _adjust_audio_volume(self, delta: float):
        self.audio.adjust_volume(delta)

    def _handle_ninja_target_click(self, pos) -> bool:
        for player in self.players:
            if player in self.eliminated_players:
                continue
            power = getattr(player, "power", None)
            handler = getattr(power, "handle_target_selection", None)
            if callable(handler) and handler(self, pos):
                return True
        return False

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
        if self.is_network_game:
            return 2
        if self.game_mode == MODE_LOCAL_MULTIPLAYER:
            return max(2, len(self.selected_characters))
        if self.game_mode == MODE_CAMPAIGN:
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
        if self.game_mode == MODE_CAMPAIGN:
            return self._vs_computer_spawns(count)
        return self._spawn_positions(count)

    def _pacman_enemy_count(self) -> int:
        if self.game_mode == MODE_ONLINE_MULTIPLAYER:
            return 2
        if self.game_mode == MODE_CAMPAIGN:
            return 1
        if self.game_mode == MODE_LOCAL_MULTIPLAYER:
            return 2
        return 1 if self.players else 0

    def _initial_pacman_enemy_spawns(self, count: int) -> list[tuple[int, int]]:
        if count <= 0:
            return []
        if not self.players:
            return [PLAYER_START_POS for _ in range(count)]
        if not self.walkable_mask:
            return self._spawn_positions(count)

        occupied = {
            (int(round(player.position.x)), int(round(player.position.y)))
            for player in self.players
        }
        center = self._walkable_center()
        prototype = self.players[0]
        offsets = [
            pygame.Vector2(0, -160),
            pygame.Vector2(160, 0),
            pygame.Vector2(0, 160),
            pygame.Vector2(-160, 0),
            pygame.Vector2(120, -120),
            pygame.Vector2(120, 120),
            pygame.Vector2(-120, 120),
            pygame.Vector2(-120, -120),
        ]

        spawns: list[tuple[int, int]] = []
        for index in range(count):
            offset = offsets[index % len(offsets)]
            spread = (index // len(offsets)) * 48
            candidate = center + offset + pygame.Vector2(spread, 0)
            spawn = self._find_valid_fallback(prototype, occupied, candidate)
            if spawn is None:
                spawn = self._find_valid_fallback(
                    prototype,
                    occupied,
                    center,
                    ignore_occupied=True,
                )
            if spawn is None:
                spawn = (int(round(center.x)), int(round(center.y)))
            spawns.append(spawn)
            occupied.add(spawn)
        return spawns

    def _character_choice(self, index: int) -> str | None:
        if not self.selected_characters:
            return None
        if 0 <= index < len(self.selected_characters):
            return self.selected_characters[index]
        return self.selected_characters[-1]

    def run(self):
        frame_count = 0
        last_diag_time = time.time()
        
        while self.running:
            frame_start = time.time()
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            frame_count += 1
            
            update_online_status(dt)
            self.handle_events()
            keys = pygame.key.get_pressed()
            self.update(dt, keys)
            self.draw()
            
            # Diagnostic: Report frame timing every 30 frames (~0.5s at 60fps)
            now = time.time()
            if now - last_diag_time >= 0.5:
                frame_elapsed = (now - frame_start) * 1000.0
                try:
                    if self.is_network_game:
                        conn_status = "CONNECTED" if (self.network and self.network.connected) else "DISCONNECTED"
                        queue_depth = len(self.network.incoming_messages) if (self.network and hasattr(self.network, 'incoming_messages')) else 0
                        print(f"[DIAG] Frame {frame_count}: dt={dt*1000:.1f}ms, elapsed={frame_elapsed:.1f}ms, status={conn_status}, queue_depth={queue_depth}", flush=True)
                except Exception:
                    pass
                last_diag_time = now

        if hasattr(self, "audio"):
            self.audio.stop_music()
        if self.network:
            try:
                print("[DIAG] Game shutting down, disconnecting network", flush=True)
            except Exception:
                pass
            self.network.disconnect()
            
        if getattr(self, "return_to_main_menu", False):
            return "main_menu"
        else:
            pygame.quit()
            return "quit"


# Backward compatibility for older imports.
Game = GameManager
