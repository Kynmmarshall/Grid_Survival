import pygame

from animation import SpriteAnimation, load_frames_from_directory
from audio import get_audio
from character_manager import DEFAULT_CHARACTER_NAME, build_animation_paths
from powers import CharacterPower, get_power_for_character
from settings import (
    DEBUG_DRAW_PLAYER_FOOTBOX,
    DEBUG_PLAYER_FOOTBOX_COLOR,
    DEBUG_VISUALS_ENABLED,
    DEBUG_DRAW_PLAYER_COLLISION,
    DEBUG_PLAYER_COLLISION_COLOR,
    PLAYER_DEFAULT_DIRECTION,
    PLAYER_FRAME_DURATION,
    PLAYER_FALL_GRAVITY,
    PLAYER_FALL_MAX_SPEED,
    PLAYER_SINK_SPEED,
    PLAYER_SCALE,
    PLAYER_SPEED,
    PLAYER_START_POS,
    PLAYER_JUMP_VELOCITY,
    PLAYER_JUMP_GRAVITY,
    PLAYER_MAX_FALL_SPEED,
    PLAYER_MAX_HEALTH,
    WINDOW_SIZE,
    SOUND_FOOTSTEP_STONE,
    SOUND_FOOTSTEP_SOFT,
    SOUND_JUMP,
    SOUND_LAND,
    SOUND_PLAYER_DROWN,
)


class Player:
    """Animated player entity with directional movement."""

    def __init__(self, position=PLAYER_START_POS, controls=None, character_name: str | None = None,
                 player_index: int = 0):
        self.is_ai = False
        self.position = pygame.Vector2(position)
        self.character_name = character_name or DEFAULT_CHARACTER_NAME

        # ── Character power ────────────────────────────────────────────────
        self.power: CharacterPower = get_power_for_character(self.character_name)
        # Runtime boost multipliers (can be set by the active power each frame)
        self._power_speed_boost: float = 1.0
        self._power_jump_boost: float = 1.0
        self._power_alpha: int = 255          # sprite transparency (e.g. ninja dash)
        self._immune_to_hazards: bool = False  # reset by game after check

        # Apply passive stat multipliers from the power
        self.speed = PLAYER_SPEED * self.power.speed_multiplier
        self._base_jump_velocity = PLAYER_JUMP_VELOCITY * self.power.jump_multiplier

        self.state = "idle"
        self.facing = PLAYER_DEFAULT_DIRECTION
        self.velocity = pygame.Vector2(0, 0)
        self.animations = self._load_animations()
        self.current_animation = self.animations[self.state][self.facing]
        self.rect = self.current_animation.image.get_rect(center=position)
        self._feet_mask = None
        self._feet_mask_count = 0
        self._collision_mask = None
        self._collision_mask_surface_id = None
        self._collision_outline = []
        self._refresh_collision_shape(force=True)
        self.falling = False
        self.fall_velocity = 0.0
        self.fall_draw_behind = False
        self.drowning = False
        self.drown_animation_done = False
        self.drown_surface_y = None

        # Jump mechanics
        self.jumping = False
        self.jump_velocity = 0.0
        self.on_ground = True

        # Health points - player dies when health reaches 0 (falling still kills instantly)
        self.health = PLAYER_MAX_HEALTH
        self.max_health = PLAYER_MAX_HEALTH

        # Control scheme (for multiplayer)
        from powers import power_key_for_player
        self.controls = controls or {
            'up':    pygame.K_w,
            'down':  pygame.K_s,
            'left':  pygame.K_a,
            'right': pygame.K_d,
            'jump':  pygame.K_SPACE,
            'power': power_key_for_player(player_index),
        }
        # Ensure legacy control dicts without 'power' get a default
        if 'power' not in self.controls:
            self.controls['power'] = power_key_for_player(player_index)

        # ── Audio ──────────────────────────────────────────────────────────
        self._audio = get_audio()
        # Footstep cadence: fire a step sound every N seconds of movement
        self._step_timer: float = 0.0
        self._step_interval: float = 0.28   # seconds between steps at full speed
        self._was_on_ground: bool = True     # for land-sound detection

    def _load_animations(self):
        animations = {}
        animation_paths = build_animation_paths(self.character_name)
        for state, dirs in animation_paths.items():
            animations[state] = {}
            for direction, path in dirs.items():
                frames = load_frames_from_directory(path, scale=PLAYER_SCALE)
                loop = state != "death"
                animations[state][direction] = SpriteAnimation(
                    frames,
                    frame_duration=PLAYER_FRAME_DURATION,
                    loop=loop,
                )
        return animations

    def _set_state(self, state: str, direction: str):
        if self.state == state and self.facing == direction:
            return

        self.state = state
        self.facing = direction
        self.current_animation = self.animations[state][direction]
        self.current_animation.reset()
        self._refresh_collision_shape(force=True)

    def _input_vector(self, keys) -> pygame.Vector2:
        direction = pygame.Vector2(0, 0)
        if keys[self.controls['up']]:
            direction.y -= 1
        if keys[self.controls['down']]:
            direction.y += 1
        if keys[self.controls['left']]:
            direction.x -= 1
        if keys[self.controls['right']]:
            direction.x += 1
        return direction
    
    def _check_jump_input(self, keys) -> bool:
        """Check if jump key is pressed."""
        return keys[self.controls['jump']]

    def _determine_facing(self, direction: pygame.Vector2) -> str:
        if direction.y < 0:
            return "up"
        if direction.y > 0:
            return "down"
        if direction.x < 0:
            return "left"
        if direction.x > 0:
            return "right"
        return self.facing

    def update(self, dt: float, keys, walkable_mask, walkable_bounds):
        # Tick the power (cooldown, particles, active effect)
        self.power.update(dt, self)

        # Activate power on key press
        if keys[self.controls['power']]:
            self.power.try_activate(self)

        move_vector = self._input_vector(keys)
        jump_pressed = self._check_jump_input(keys)
        self._update_with_move_vector(dt, move_vector, walkable_mask, walkable_bounds, jump_pressed)

    def _update_with_move_vector(
        self,
        dt: float,
        move_vector: pygame.Vector2,
        walkable_mask,
        walkable_bounds,
        jump_pressed: bool = False,
    ):
        if self.falling:
            self._update_fall(dt)
            self.current_animation.update(dt)
            self.rect.center = (round(self.position.x), round(self.position.y))
            return

        if self.drowning:
            self._update_drown(dt)
            self.rect.center = (round(self.position.x), round(self.position.y))
            return

        # Handle jumping
        if self.jumping:
            self._update_jump(dt, move_vector, walkable_mask)
            self.current_animation.update(dt)
            self.rect.center = (round(self.position.x), round(self.position.y))
            return

        # Apply runtime power boosts to speed and jump
        effective_speed = self.speed * self._power_speed_boost
        effective_jump_velocity = self._base_jump_velocity * self._power_jump_boost

        # Check if on ground
        self.on_ground = self._is_over_platform(self.position, walkable_mask)

        # Initiate jump
        if jump_pressed and self.on_ground:
            self.jumping = True
            self.jump_velocity = effective_jump_velocity
            self.on_ground = False
            self._was_on_ground = False
            self._audio.play_sfx(SOUND_JUMP, volume=0.5, volume_jitter=0.06, max_instances=2)

        desired_facing = (
            self._determine_facing(move_vector)
            if move_vector.length_squared() > 0
            else self.facing
        )

        # Detect landing (was airborne last frame, now on ground)
        just_landed = (not self._was_on_ground) and self.on_ground and not self.jumping
        self._was_on_ground = self.on_ground

        left_playable = False
        if move_vector.length_squared() > 0:
            move_vector = move_vector.normalize()
            displacement = move_vector * effective_speed * dt
            self.velocity = move_vector * effective_speed
            left_playable = not self._attempt_move(displacement, walkable_mask)
            self._set_state("run", desired_facing)

            # Footstep sound — throttled by _step_timer
            if self.on_ground:
                self._step_timer += dt
                interval = self._step_interval / max(0.5, self._power_speed_boost)
                if self._step_timer >= interval:
                    self._step_timer = 0.0
                    self._audio.play_sfx_random(
                        SOUND_FOOTSTEP_STONE,
                        volume=0.45,
                        volume_jitter=0.08,
                        max_instances=2,
                    )
        else:
            self._step_timer = 0.0
            self.velocity.update(0, 0)
            self._set_state("idle", desired_facing)
            if walkable_mask and not self._is_over_platform(self.position, walkable_mask):
                left_playable = True

        # Land sound
        if just_landed:
            self._audio.play_sfx(SOUND_LAND, volume=0.55, volume_jitter=0.08, max_instances=2)

        if left_playable:
            self._start_fall(walkable_bounds)
            self._update_fall(dt)

        self.current_animation.update(dt)
        self.rect.center = (round(self.position.x), round(self.position.y))

    def _attempt_move(self, delta: pygame.Vector2, walkable_mask) -> bool:
        proposed = self.position + delta
        if self._is_over_platform(proposed, walkable_mask):
            self.position = proposed
            return True

        # try separating axes so the player can slide along platform edges
        if delta.x:
            proposed_x = pygame.Vector2(self.position.x + delta.x, self.position.y)
            if self._is_over_platform(proposed_x, walkable_mask):
                self.position.x = proposed_x.x
                return True

        if delta.y:
            proposed_y = pygame.Vector2(self.position.x, self.position.y + delta.y)
            if self._is_over_platform(proposed_y, walkable_mask):
                self.position.y = proposed_y.y
                return True

        self.position = proposed
        return False

    def _is_over_platform(self, position: pygame.Vector2, walkable_mask) -> bool:
        if walkable_mask is None:
            return True

        feet_rect = self._feet_rect(position)
        feet_mask = self._feet_mask_for_rect(feet_rect)
        overlap = walkable_mask.overlap_area(feet_mask, feet_rect.topleft)
        return overlap == self._feet_mask_count

    def _feet_rect(self, position: pygame.Vector2) -> pygame.Rect:
        width = max(4, int(self.rect.width * 0.03))
        height = max(4, int(self.rect.height * 0.03))
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (
            round(position.x),
            round(position.y + self.rect.height * 0.25),
        )
        return rect

    def _refresh_collision_shape(self, force: bool = False):
        surface = self.current_animation.image
        surface_id = id(surface)
        if not force and surface_id == self._collision_mask_surface_id:
            return
        self._collision_mask = pygame.mask.from_surface(surface)
        self._collision_mask_surface_id = surface_id
        self._collision_outline = self._collision_mask.outline()

    def draw(self, surface: pygame.Surface):
        frame = self.current_animation.image
        # Apply power-driven transparency (e.g. ninja invisibility)
        if self._power_alpha < 255:
            frame = frame.copy()
            frame.set_alpha(self._power_alpha)
        surface.blit(frame, self.rect.topleft)

        # Draw power particles / active effects
        self.power.draw(surface, self)

        if DEBUG_VISUALS_ENABLED and DEBUG_DRAW_PLAYER_FOOTBOX:
            feet_rect = self._feet_rect(self.position)
            pygame.draw.rect(surface, DEBUG_PLAYER_FOOTBOX_COLOR, feet_rect, 1)
        if DEBUG_VISUALS_ENABLED and DEBUG_DRAW_PLAYER_COLLISION:
            self._refresh_collision_shape()
            if len(self._collision_outline) >= 2:
                offset_x, offset_y = self.rect.topleft
                outline_points = [
                    (offset_x + point[0], offset_y + point[1])
                    for point in self._collision_outline
                ]
                pygame.draw.lines(
                    surface,
                    DEBUG_PLAYER_COLLISION_COLOR,
                    True,
                    outline_points,
                    1,
                )

    def reset(self):
        self.position = pygame.Vector2(PLAYER_START_POS)
        self.velocity.update(0, 0)
        self.state = "idle"
        self.facing = PLAYER_DEFAULT_DIRECTION
        self.current_animation = self.animations[self.state][self.facing]
        self.current_animation.reset()
        self.rect.center = PLAYER_START_POS
        self.falling = False
        self.fall_velocity = 0.0
        self.fall_draw_behind = False
        self.drowning = False
        self.drown_animation_done = False
        self.drown_surface_y = None
        self.jumping = False
        self.jump_velocity = 0.0
        self.on_ground = True
        self._power_speed_boost = 1.0
        self._power_jump_boost = 1.0
        self._power_alpha = 255
        self._immune_to_hazards = False
        # Reset health
        self.health = PLAYER_MAX_HEALTH
        self.max_health = PLAYER_MAX_HEALTH
        self.power.reset()
        self._refresh_collision_shape(force=True)

    def _feet_mask_for_rect(self, rect: pygame.Rect) -> pygame.mask.Mask:
        size = rect.size
        if self._feet_mask is None or self._feet_mask.get_size() != size:
            self._feet_mask = pygame.mask.Mask(size)
            self._feet_mask.fill()
            self._feet_mask_count = self._feet_mask.count()
        return self._feet_mask

    def _start_fall(self, walkable_bounds):
        if self.falling:
            return
        self.falling = True
        self.fall_velocity = 0.0
        self.velocity.update(0, 0)
        self.drowning = False
        self.drown_animation_done = False
        self.drown_surface_y = None
        if walkable_bounds:
            feet_rect = self._feet_rect(self.position)
            inside_bounds = walkable_bounds.contains(feet_rect)
            gap_threshold = walkable_bounds.top + walkable_bounds.height * 0.6
            falling_through_gap = inside_bounds and feet_rect.bottom <= gap_threshold
            above_top_edge = feet_rect.bottom <= walkable_bounds.top
            # Only draw behind when falling through interior gaps or leaving via the back (top) edge.
            self.fall_draw_behind = falling_through_gap or above_top_edge
        else:
            self.fall_draw_behind = False

    def _update_fall(self, dt: float):
        self.fall_velocity = min(
            self.fall_velocity + PLAYER_FALL_GRAVITY * dt, PLAYER_FALL_MAX_SPEED
        )
        self.position.y += self.fall_velocity * dt
        self.velocity.y = self.fall_velocity

        bottom_limit = WINDOW_SIZE[1] + self.rect.height
        if self.position.y - self.rect.height / 2 > WINDOW_SIZE[1]:
            self.position.y = min(self.position.y, bottom_limit)
    
    def _update_jump(self, dt: float, move_vector: pygame.Vector2, walkable_mask):
        """Update jump physics and horizontal movement during jump."""
        # Apply gravity to jump velocity
        self.jump_velocity = min(
            self.jump_velocity + PLAYER_JUMP_GRAVITY * dt, PLAYER_MAX_FALL_SPEED
        )
        
        # Update vertical position
        self.position.y += self.jump_velocity * dt
        self.velocity.y = self.jump_velocity
        
        # Allow horizontal movement during jump
        if move_vector.length_squared() > 0:
            move_vector = move_vector.normalize()
            h_speed = self.speed * self._power_speed_boost
            horizontal_displacement = pygame.Vector2(move_vector.x * h_speed * dt, 0)
            proposed_x = self.position + horizontal_displacement
            if self._is_over_platform(proposed_x, walkable_mask):
                self.position.x = proposed_x.x
        
        # Check if landed on platform
        if self.jump_velocity > 0:  # Falling down
            if self._is_over_platform(self.position, walkable_mask):
                self.jumping = False
                self.jump_velocity = 0.0
                self.on_ground = True
        
        # Check if fell off platform
        if not self._is_over_platform(self.position, walkable_mask) and self.jump_velocity > 0:
            self.jumping = False
            self.falling = True
            self.fall_velocity = self.jump_velocity

    def draws_behind_map(self) -> bool:
        return (self.falling or self.drowning) and self.fall_draw_behind

    def get_feet_rect(self) -> pygame.Rect:
        return self._feet_rect(self.position)

    def is_falling(self) -> bool:
        return self.falling

    def is_drowning(self) -> bool:
        return self.drowning

    def start_drowning(self, surface_y: float, draw_behind: bool | None = None):
        if self.drowning:
            return
        self.falling = False
        self.fall_velocity = 0.0
        self.velocity.update(0, 0)
        self.drowning = True
        self.drown_animation_done = False
        self.drown_surface_y = surface_y
        self.position.y = surface_y - self.rect.height * 0.25
        self._set_state("death", self.facing)
        if draw_behind is not None:
            self.fall_draw_behind = draw_behind
        self._audio.play_sfx(SOUND_PLAYER_DROWN, volume=0.65, max_instances=1)

    def _update_drown(self, dt: float):
        if not self.drowning:
            return
        if not self.drown_animation_done:
            self.current_animation.update(dt)
            if self.current_animation.finished:
                self.drown_animation_done = True
            return

        # After the death animation holds, sink slowly beneath the water surface.
        self.position.y += PLAYER_SINK_SPEED * dt
        self.velocity.y = PLAYER_SINK_SPEED
        max_center_y = WINDOW_SIZE[1] - self.rect.height / 3.5
        if self.position.y > max_center_y:
            self.position.y = max_center_y
            self.velocity.y = 0.0