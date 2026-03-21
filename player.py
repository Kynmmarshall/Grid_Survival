import pygame

from audio import get_audio
from animation import SpriteAnimation, load_frames_from_directory
from character_manager import DEFAULT_CHARACTER_NAME, build_animation_paths
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
    SOUND_PLAYER_JUMP,
    WINDOW_SIZE,
)


class Player:
    """Animated player entity with directional movement."""

    def __init__(self, position=PLAYER_START_POS, controls=None, character_name: str | None = None):
        self.is_ai = False
        self.position = pygame.Vector2(position)
        self.speed = PLAYER_SPEED
        self.state = "idle"
        self.facing = PLAYER_DEFAULT_DIRECTION
        self.velocity = pygame.Vector2(0, 0)
        self.character_name = character_name or DEFAULT_CHARACTER_NAME
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
        self.z = 0.0          # Height off the ground (Z-axis)
        self.z_velocity = 0.0 # Vertical velocity (Z-axis)
        self.on_ground = True
        
        # Control scheme (for multiplayer)
        self.controls = controls or {
            'up': pygame.K_w,
            'down': pygame.K_s,
            'left': pygame.K_a,
            'right': pygame.K_d,
            'jump': pygame.K_SPACE
        }
        self.audio = get_audio()

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

    def die(self):
        """Trigger death state. Stop movement and stay."""
        if self.state == "death":
            return
        self.state = "death"
        self.falling = False
        self.drowning = False
        self.jumping = False
        self.velocity.update(0, 0)
        self.current_animation = self.animations["death"][self.facing]
        self.current_animation.reset()

    def _update_death(self, dt: float):
        """Update death animation."""
        if not self.current_animation.finished:
            self.current_animation.update(dt)

    def get_hitbox(self) -> pygame.Rect:
        """Get a tighter hitbox for hazard collision."""
        # Shrink the rect horizontally and vertically to avoid cheap hits
        shrink_x = -int(self.rect.width * 0.4)
        shrink_y = -int(self.rect.height * 0.4)
        return self.rect.inflate(shrink_x, shrink_y)

    def update(self, dt: float, keys, walkable_mask, walkable_bounds):
        move_vector = self._input_vector(keys)
        # ... (rest is handled inside _update_with_move_vector)
        self._update_with_move_vector(dt, move_vector, walkable_mask, walkable_bounds, self._check_jump_input(keys))

    def _update_with_move_vector(
        self,
        dt: float,
        move_vector: pygame.Vector2,
        walkable_mask,
        walkable_bounds,
        jump_pressed: bool = False,
    ):
        if self.state == "death":
            self._update_death(dt)
            return

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
            self._update_jump(dt, move_vector, walkable_mask, walkable_bounds)
            self.current_animation.update(dt)
            # Center represents ground contact point
            self.rect.center = (round(self.position.x), round(self.position.y))
            return

        # Check if on ground
        self.on_ground = self._is_over_platform(self.position, walkable_mask)
        
        # Initiate jump
        if jump_pressed and self.on_ground:
            self.jumping = True
            self.z_velocity = PLAYER_JUMP_VELOCITY
            self.on_ground = False
            if self.audio:
                self.audio.play_sfx(SOUND_PLAYER_JUMP, volume=0.65)

        desired_facing = (
            self._determine_facing(move_vector)
            if move_vector.length_squared() > 0
            else self.facing
        )

        left_playable = False
        if move_vector.length_squared() > 0:
            move_vector = move_vector.normalize()
            displacement = move_vector * self.speed * dt
            self.velocity = move_vector * self.speed
            left_playable = not self._attempt_move(displacement, walkable_mask)
            self._set_state("run", desired_facing)
        else:
            self.velocity.update(0, 0)
            self._set_state("idle", desired_facing)
            if walkable_mask and not self._is_over_platform(self.position, walkable_mask):
                left_playable = True

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
        # Draw Shadow at ground position
        if self.jumping and self.z > 0:
            shadow_rect = pygame.Rect(0, 0, self.rect.width * 0.6, self.rect.height * 0.2)
            shadow_rect.center = (self.rect.centerx, self.rect.bottom - 5)
            # Scale shadow relative to height
            scale = max(0.5, 1.0 - (self.z / 300))
            shadow_w = int(shadow_rect.width * scale)
            shadow_h = int(shadow_rect.height * scale)
            shadow_s = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow_s, (0, 0, 0, 100), shadow_s.get_rect())
            surface.blit(shadow_s, (shadow_rect.centerx - shadow_w//2, shadow_rect.centery - shadow_h//2))

        # Apply Z-offset to draw position
        draw_rect = self.rect.copy()
        draw_rect.y -= round(self.z)
        surface.blit(self.current_animation.image, draw_rect.topleft)

        if DEBUG_VISUALS_ENABLED and DEBUG_DRAW_PLAYER_FOOTBOX:
            feet_rect = self._feet_rect(self.position)
            # Feet rect tracks the ground position
            pygame.draw.rect(surface, DEBUG_PLAYER_FOOTBOX_COLOR, feet_rect, 1)
        if DEBUG_VISUALS_ENABLED and DEBUG_DRAW_PLAYER_COLLISION:
            self._refresh_collision_shape()
            if len(self._collision_outline) >= 2:
                offset_x, offset_y = draw_rect.topleft # Draw collision shape at JUMP height too? Generally yes for visual clarity
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
        self.z = 0.0
        self.z_velocity = 0.0
        self.on_ground = True
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
    
    def _update_jump(self, dt: float, move_vector: pygame.Vector2, walkable_mask, walkable_bounds):
        """
        Update jump physics (Z-axis) and allow air control (X/Y axis).
        Moves the ground position independent of height.
        """
        # 1. Apply Gravity to Z-Velocity
        self.z_velocity -= PLAYER_JUMP_GRAVITY * dt
        self.z_velocity = max(-PLAYER_MAX_FALL_SPEED, self.z_velocity)

        # 2. Update Z-Position
        self.z += self.z_velocity * dt

        # 3. Handle Horizontal Movement (Air Control)
        if move_vector.length_squared() > 0:
            move_vector = move_vector.normalize()
            displacement = move_vector * self.speed * dt
            
            # Update facing direction visually
            self.facing = self._determine_facing(move_vector)
            self._set_state("run", self.facing) # Or custom 'jump' anim state if available
            
            # Apply movement to ground position
            # We don't check for 'over platform' here strictly, 
            # allowing jumping over gaps. But check bounds if available.
            proposed_pos = self.position + displacement
            
            # Optional: constrain to world bounds so we don't jump off screen 
            if walkable_bounds:
                # Basic clamping to bounds
                if walkable_bounds.collidepoint(proposed_pos.x, proposed_pos.y):
                    self.position = proposed_pos
                else:
                    # Allow movement if it brings us closer to bounds or slides along
                    pass # Simplified: Just accept move for now or implement clamp
                    self.position = proposed_pos 
            else:
                 self.position = proposed_pos

        else:
             self._set_state("idle", self.facing)

        # 4. Check Landing
        if self.z <= 0:
            self.z = 0.0
            self.z_velocity = 0.0
            self.jumping = False
            
            # Check if we landed on solid ground or a pit
            if self._is_over_platform(self.position, walkable_mask):
                self.on_ground = True
            else:
                # Landed in a pit -> start falling
                self.on_ground = False
                self._start_fall(walkable_bounds)

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
