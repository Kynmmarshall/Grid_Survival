import pygame

from animation import SpriteAnimation, load_frames_from_directory
from settings import (
    DEBUG_DRAW_PLAYER_FOOTBOX,
    DEBUG_PLAYER_FOOTBOX_COLOR,
    DEBUG_VISUALS_ENABLED,
    PLAYER_ANIMATION_PATHS,
    PLAYER_DEFAULT_DIRECTION,
    PLAYER_FRAME_DURATION,
    PLAYER_FALL_GRAVITY,
    PLAYER_FALL_MAX_SPEED,
    PLAYER_SINK_SPEED,
    PLAYER_SCALE,
    PLAYER_SPEED,
    PLAYER_START_POS,
    WINDOW_SIZE,
)


class Player:
    """Animated player entity with directional movement."""

    def __init__(self, position=PLAYER_START_POS):
        self.position = pygame.Vector2(position)
        self.speed = PLAYER_SPEED
        self.state = "idle"
        self.facing = PLAYER_DEFAULT_DIRECTION
        self.velocity = pygame.Vector2(0, 0)
        self.animations = self._load_animations()
        self.current_animation = self.animations[self.state][self.facing]
        self.rect = self.current_animation.image.get_rect(center=position)
        self._feet_mask = None
        self._feet_mask_count = 0
        self.falling = False
        self.fall_velocity = 0.0
        self.fall_draw_behind = False
        self.drowning = False
        self.drown_animation_done = False
        self.drown_surface_y = None

    def _load_animations(self):
        animations = {}
        for state, dirs in PLAYER_ANIMATION_PATHS.items():
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

    def _input_vector(self, keys) -> pygame.Vector2:
        direction = pygame.Vector2(0, 0)
        if keys[pygame.K_w]:
            direction.y -= 1
        if keys[pygame.K_s]:
            direction.y += 1
        if keys[pygame.K_a]:
            direction.x -= 1
        if keys[pygame.K_d]:
            direction.x += 1
        return direction

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
        if self.falling:
            self._update_fall(dt)
            self.current_animation.update(dt)
            self.rect.center = (round(self.position.x), round(self.position.y))
            return

        if self.drowning:
            self._update_drown(dt)
            self.rect.center = (round(self.position.x), round(self.position.y))
            return

        move_vector = self._input_vector(keys)
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
        width = max(4, int(self.rect.width * 0.15))
        height = max(4, int(self.rect.height * 0.03))
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (
            round(position.x),
            round(position.y + self.rect.height * 0.25),
        )
        return rect

    def draw(self, surface: pygame.Surface):
        surface.blit(self.current_animation.image, self.rect.topleft)
        if DEBUG_VISUALS_ENABLED and DEBUG_DRAW_PLAYER_FOOTBOX:
            feet_rect = self._feet_rect(self.position)
            pygame.draw.rect(surface, DEBUG_PLAYER_FOOTBOX_COLOR, feet_rect, 1)

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
            if walkable_bounds.contains(feet_rect):
                self.fall_draw_behind = True
            else:
                self.fall_draw_behind = self.position.y <= walkable_bounds.centery
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
