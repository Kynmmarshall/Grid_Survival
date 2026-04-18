import math
from typing import Any, Optional

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
    POWER_ORBS_REQUIRED,
    ORB_SHIELD_WARNING,
    SHIELD_EFFECT_PATH,
    VOID_WALK_WING_PATH,
)


_SHIELD_EFFECT_SURFACE: pygame.Surface | None = None
_VOID_WALK_WING_CACHE: dict[
    int, tuple[list[pygame.Surface], list[pygame.Surface], list[pygame.Surface], list[pygame.Surface]]
] = {}


def _get_shield_effect_surface() -> pygame.Surface | None:
    global _SHIELD_EFFECT_SURFACE
    if _SHIELD_EFFECT_SURFACE is not None:
        return _SHIELD_EFFECT_SURFACE
    if SHIELD_EFFECT_PATH and SHIELD_EFFECT_PATH.exists():
        try:
            _SHIELD_EFFECT_SURFACE = pygame.image.load(SHIELD_EFFECT_PATH.as_posix()).convert_alpha()
        except Exception:
            _SHIELD_EFFECT_SURFACE = None
    else:
        _SHIELD_EFFECT_SURFACE = None
    return _SHIELD_EFFECT_SURFACE


def _get_void_walk_wing_frames(
    target_size: int,
) -> tuple[list[pygame.Surface], list[pygame.Surface], list[pygame.Surface], list[pygame.Surface]] | None:
    """
    Returns (left_light, right_light, left_dark, right_dark) where each is [frame0, frame1].
    Uses the bundled CC0 wing spritesheet (2x2 of 32x32 cells).
    """
    target_size = int(target_size)
    if target_size <= 0:
        return None

    cached = _VOID_WALK_WING_CACHE.get(target_size)
    if cached is not None:
        return cached

    if not VOID_WALK_WING_PATH or not VOID_WALK_WING_PATH.exists():
        return None

    try:
        sheet = pygame.image.load(VOID_WALK_WING_PATH.as_posix()).convert_alpha()
    except Exception:
        return None

    cell = 32
    if sheet.get_width() < cell * 2 or sheet.get_height() < cell * 2:
        return None

    def extract(col: int, row: int) -> pygame.Surface:
        frame = pygame.Surface((cell, cell), pygame.SRCALPHA)
        frame.blit(sheet, (0, 0), (col * cell, row * cell, cell, cell))
        if target_size != cell:
            frame = pygame.transform.smoothscale(frame, (target_size, target_size))
        return frame

    def tint_black(src: pygame.Surface) -> pygame.Surface:
        out = src.copy()
        tint = pygame.Surface(out.get_size(), pygame.SRCALPHA)
        tint.fill((0, 0, 0, 255))
        out.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return out

    # Column 0 = left wing, Column 1 = right wing; Row 0/1 = flap frames.
    left_light = [extract(0, 0), extract(0, 1)]
    right_light = [extract(1, 0), extract(1, 1)]
    left_dark = [tint_black(frame) for frame in left_light]
    right_dark = [tint_black(frame) for frame in right_light]

    _VOID_WALK_WING_CACHE[target_size] = (left_light, right_light, left_dark, right_dark)
    return _VOID_WALK_WING_CACHE[target_size]


class Player:
    """Animated player entity with directional movement."""

    def __init__(self, position=PLAYER_START_POS, controls=None, character_name: str | None = None):
        self.is_ai = False
        self._eliminated = False
        self.spawn_position = pygame.Vector2(position)
        self.position = self.spawn_position.copy()
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
            'jump': pygame.K_SPACE,
            'power': pygame.K_q,
        }
        self.audio = get_audio()
        self.power = None
        self.power_key = None
        self.power_orb_charges = 0
        self.passive_speed_multiplier = 1.0
        self.passive_jump_multiplier = 1.0
        self._power_speed_boost = 1.0
        self._power_jump_boost = 1.0
        self._orb_speed_boost = 1.0
        self._shield_timer = 0.0
        self._shield_warning_threshold = ORB_SHIELD_WARNING
        self._freeze_timer = 0.0
        self._void_walk_timer = 0.0
        self._status_flash_timer = 0.0
        self._immune_to_hazards = False
        self._power_alpha = 255
        self._death_fade_alpha = 255
        self._active_orb_label: str | None = None
        self._active_orb_timer = 0.0
        self._active_orb_indefinite = False
        self._active_orb_duration = 0.0
        self._extra_lives = 0  # Extra lives from LIFE orbs

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

    def attach_power(self, power, key: int | None):
        self.power = power
        self.power_key = key
        if power:
            self.passive_speed_multiplier = getattr(power, "speed_multiplier", 1.0) or 1.0
            self.passive_jump_multiplier = getattr(power, "jump_multiplier", 1.0) or 1.0
        else:
            self.passive_speed_multiplier = 1.0
            self.passive_jump_multiplier = 1.0

    def set_active_orb(self, label: str, duration: float | None = None):
        self._active_orb_label = label
        if duration is None:
            self._active_orb_timer = 0.0
            self._active_orb_indefinite = True
            self._active_orb_duration = 0.0
        else:
            self._active_orb_timer = max(0.0, duration)
            self._active_orb_indefinite = False
            self._active_orb_duration = self._active_orb_timer

    def clear_active_orb(self, label: str | None = None):
        if label and self._active_orb_label != label:
            return
        self._active_orb_label = None
        self._active_orb_timer = 0.0
        self._active_orb_indefinite = False
        self._active_orb_duration = 0.0

    def get_active_orb_status(self) -> tuple[Optional[str], float, bool, float]:
        return (
            self._active_orb_label,
            self._active_orb_timer,
            self._active_orb_indefinite,
            self._active_orb_duration,
        )

    def add_power_orb_charge(self, amount: int = 1) -> int:
        self.power_orb_charges = min(POWER_ORBS_REQUIRED, self.power_orb_charges + amount)
        return self.power_orb_charges

    def try_use_power(self, game=None) -> bool:
        if not self.power or self.power_orb_charges < POWER_ORBS_REQUIRED:
            return False
        if self.power.try_activate(self, game):
            self.power_orb_charges -= POWER_ORBS_REQUIRED
            if self.power_orb_charges <= 0:
                self.clear_active_orb("Power Charge")
            return True
        return False

    def add_shield(self, duration: float):
        self._shield_timer = max(duration, self._shield_timer)

    def has_active_shield(self) -> bool:
        return self._shield_timer > 0

    def add_life(self):
        """Add an extra life from a LIFE orb."""
        self._extra_lives += 1
        print(f"DEBUG: Player now has {self._extra_lives} extra lives")

    def has_extra_life(self) -> bool:
        """Check if player has an extra life available."""
        return self._extra_lives > 0

    def use_life(self) -> bool:
        """Use an extra life to revive. Returns True if life was used."""
        if self._extra_lives > 0:
            self._extra_lives -= 1
            return True
        return False

    def apply_freeze(self, duration: float):
        self._freeze_timer = duration

    def is_frozen(self) -> bool:
        return self._freeze_timer > 0

    def enable_void_walk(self, duration: float):
        self._void_walk_timer = max(duration, self._void_walk_timer)

    def has_void_walk(self) -> bool:
        return self._void_walk_timer > 0

    def _tick_status_effects(self, dt: float):
        if self._shield_timer > 0:
            self._shield_timer = max(0.0, self._shield_timer - dt)
        if self._freeze_timer > 0:
            self._freeze_timer = max(0.0, self._freeze_timer - dt)
        if self._void_walk_timer > 0:
            self._void_walk_timer = max(0.0, self._void_walk_timer - dt)
        if self._active_orb_label and not self._active_orb_indefinite:
            if self._active_orb_timer > 0:
                self._active_orb_timer = max(0.0, self._active_orb_timer - dt)
                if self._active_orb_timer == 0:
                    self._active_orb_label = None
                    self._active_orb_duration = 0.0
        if self._active_orb_label == "Power Charge" and self.power_orb_charges <= 0:
            self._active_orb_label = None
            self._active_orb_timer = 0.0
            self._active_orb_indefinite = False
            self._active_orb_duration = 0.0
        self._status_flash_timer += dt

    def _speed_multiplier(self) -> float:
        """Combine all speed buffs into a single multiplier."""
        base = self.passive_speed_multiplier or 1.0
        power = self._power_speed_boost or 1.0
        orb = self._orb_speed_boost or 1.0
        return max(0.0, base * power * orb)

    def _jump_multiplier(self) -> float:
        """Combine jump buffs before applying jump velocity."""
        base = self.passive_jump_multiplier or 1.0
        power = self._power_jump_boost or 1.0
        return max(0.0, base * power)

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
        self._power_alpha = 255
        self._death_fade_alpha = 255
        self.current_animation = self.animations["death"][self.facing]
        self.current_animation.reset()

    def _update_death(self, dt: float):
        """Update death animation."""
        self._death_fade_alpha = max(0, int(self._death_fade_alpha - 220 * dt))
        if not self.current_animation.finished:
            self.current_animation.update(dt)

    def get_hitbox(self) -> pygame.Rect:
        """Get a tighter hitbox for hazard collision."""
        # Shrink the rect horizontally and vertically to avoid cheap hits
        shrink_x = -int(self.rect.width * 0.4)
        shrink_y = -int(self.rect.height * 0.4)
        return self.rect.inflate(shrink_x, shrink_y)

    def update(self, dt: float, keys, walkable_mask, walkable_bounds):
        self._tick_status_effects(dt)
        if self.power and hasattr(self.power, "blocks_player_motion") and self.power.blocks_player_motion():
            if hasattr(self.power, "update_target_cursor"):
                self.power.update_target_cursor(dt, keys, self, walkable_mask, walkable_bounds)
            self.velocity.update(0, 0)
            self.rect.center = (round(self.position.x), round(self.position.y))
            return
        move_vector = self._input_vector(keys)
        jump_pressed = self._check_jump_input(keys)
        if self.is_frozen():
            move_vector = pygame.Vector2(0, 0)
            jump_pressed = False
        self._update_with_move_vector(dt, move_vector, walkable_mask, walkable_bounds, jump_pressed)

    def update_from_input_state(
        self,
        dt: float,
        input_state: dict[str, Any] | Any,
        walkable_mask,
        walkable_bounds,
    ):
        """Update from a simple boolean mapping instead of pygame key state."""
        self._tick_status_effects(dt)
        data = input_state if isinstance(input_state, dict) else {}
        move_vector = pygame.Vector2(
            float(bool(data.get("right", False))) - float(bool(data.get("left", False))),
            float(bool(data.get("down", False))) - float(bool(data.get("up", False))),
        )
        jump_pressed = bool(data.get("jump", False))
        if self.is_frozen():
            move_vector = pygame.Vector2(0, 0)
            jump_pressed = False
        self._update_with_move_vector(dt, move_vector, walkable_mask, walkable_bounds, jump_pressed)

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

        current_speed = self.speed * self._speed_multiplier()

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
            self.z_velocity = PLAYER_JUMP_VELOCITY * self._jump_multiplier()
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
            displacement = move_vector * current_speed * dt
            self.velocity = move_vector * current_speed
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
        if self.has_void_walk():
            return True
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
        death_alpha = self._death_fade_alpha if self.state == "death" else 255
        render_alpha = min(self._power_alpha, death_alpha)
        if render_alpha <= 0:
            return

        # Draw Shadow at ground position
        if self.jumping and self.z > 0:
            shadow_rect = pygame.Rect(0, 0, self.rect.width * 0.6, self.rect.height * 0.2)
            shadow_rect.center = (self.rect.centerx, self.rect.bottom - 5)
            # Scale shadow relative to height
            scale = max(0.5, 1.0 - (self.z / 300))
            shadow_w = int(shadow_rect.width * scale)
            shadow_h = int(shadow_rect.height * scale)
            shadow_s = pygame.Surface((shadow_w, shadow_h), pygame.SRCALPHA)
            shadow_alpha = int(100 * (death_alpha / 255))
            pygame.draw.ellipse(shadow_s, (0, 0, 0, shadow_alpha), shadow_s.get_rect())
            surface.blit(shadow_s, (shadow_rect.centerx - shadow_w//2, shadow_rect.centery - shadow_h//2))

        # Apply Z-offset to draw position
        draw_rect = self.rect.copy()
        draw_rect.y -= round(self.z)

        wing_blits_behind: list[tuple[pygame.Surface, tuple[int, int]]] = []
        wing_blits_front: list[tuple[pygame.Surface, tuple[int, int]]] = []
        if self._has_void_walk_wings():
            wing_blits_behind, wing_blits_front = self._void_walk_wing_blits(
                draw_rect, render_alpha / 255.0
            )
            for wing_surface, wing_pos in wing_blits_behind:
                surface.blit(wing_surface, wing_pos)
        frame = self.current_animation.image
        if render_alpha != 255:
            frame = frame.copy()
            frame.set_alpha(render_alpha)
        surface.blit(frame, draw_rect.topleft)

        for wing_surface, wing_pos in wing_blits_front:
            surface.blit(wing_surface, wing_pos)

        death_opacity = death_alpha / 255.0
        if self._has_speed_orb_glow():
            self._draw_speed_orb_glow(surface, draw_rect, death_opacity)
        if self._shield_timer > 0:
            self._draw_shield_overlay(surface, draw_rect, death_opacity)
        if self.is_frozen():
            self._draw_freeze_overlay(surface, draw_rect, death_opacity)
        if self.power_orb_charges > 0 and self.state != "death":
            self._draw_power_orb_icons(surface)

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
        self._eliminated = False
        self.position = self.spawn_position.copy()
        self.velocity.update(0, 0)
        self.state = "idle"
        self.facing = PLAYER_DEFAULT_DIRECTION
        self.current_animation = self.animations[self.state][self.facing]
        self.current_animation.reset()
        self.rect.center = (round(self.position.x), round(self.position.y))
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
        self.power_orb_charges = 0
        self._shield_timer = 0.0
        self._freeze_timer = 0.0
        self._void_walk_timer = 0.0
        self._orb_speed_boost = 1.0
        if hasattr(self, "_orb_speed_timer"):
            del self._orb_speed_timer
        self._power_speed_boost = 1.0
        self._power_jump_boost = 1.0
        self._status_flash_timer = 0.0
        self._immune_to_hazards = False
        self._power_alpha = 255
        self._death_fade_alpha = 255
        self.clear_active_orb()
        self._extra_lives = 0
        self._refresh_collision_shape(force=True)

    def snapshot_state(self) -> dict[str, Any]:
        orb_label, orb_timer, orb_indefinite, orb_duration = self.get_active_orb_status()
        return {
            "x": float(self.position.x),
            "y": float(self.position.y),
            "facing": self.facing,
            "state": self.state,
            "falling": self.falling,
            "fall_velocity": float(self.fall_velocity),
            "drowning": self.drowning,
            "jumping": self.jumping,
            "z": float(self.z),
            "z_velocity": float(self.z_velocity),
            "on_ground": bool(self.on_ground),
            "velocity_x": float(self.velocity.x),
            "velocity_y": float(self.velocity.y),
            "character_name": self.character_name,
            "power_orb_charges": int(self.power_orb_charges),
            "shield_timer": float(self._shield_timer),
            "freeze_timer": float(self._freeze_timer),
            "power_alpha": int(self._power_alpha),
            "power_speed_boost": float(self._power_speed_boost),
            "power_jump_boost": float(self._power_jump_boost),
            "orb_speed_boost": float(self._orb_speed_boost),
            "active_orb_label": orb_label,
            "active_orb_timer": float(orb_timer),
            "active_orb_indefinite": bool(orb_indefinite),
            "active_orb_duration": float(orb_duration),
            "eliminated": bool(self._eliminated),
            "extra_lives": int(self._extra_lives),
        }

    def apply_snapshot_state(self, snapshot: dict[str, Any]):
        if not isinstance(snapshot, dict):
            return

        self.position = pygame.Vector2(
            float(snapshot.get("x", self.position.x)),
            float(snapshot.get("y", self.position.y)),
        )
        self.velocity = pygame.Vector2(
            float(snapshot.get("velocity_x", self.velocity.x)),
            float(snapshot.get("velocity_y", self.velocity.y)),
        )
        self.fall_velocity = float(snapshot.get("fall_velocity", self.fall_velocity))
        self.falling = bool(snapshot.get("falling", self.falling))
        self.drowning = bool(snapshot.get("drowning", self.drowning))
        self.jumping = bool(snapshot.get("jumping", self.jumping))
        self.z = float(snapshot.get("z", self.z))
        self.z_velocity = float(snapshot.get("z_velocity", self.z_velocity))
        self.on_ground = bool(snapshot.get("on_ground", self.on_ground))
        self.power_orb_charges = int(snapshot.get("power_orb_charges", self.power_orb_charges))
        self._shield_timer = float(snapshot.get("shield_timer", self._shield_timer))
        self._freeze_timer = float(snapshot.get("freeze_timer", self._freeze_timer))
        self._power_alpha = int(snapshot.get("power_alpha", self._power_alpha))
        self._power_speed_boost = float(snapshot.get("power_speed_boost", self._power_speed_boost))
        self._power_jump_boost = float(snapshot.get("power_jump_boost", self._power_jump_boost))
        self._orb_speed_boost = float(snapshot.get("orb_speed_boost", self._orb_speed_boost))
        self._eliminated = bool(snapshot.get("eliminated", self._eliminated))
        self._active_orb_label = snapshot.get("active_orb_label")
        self._extra_lives = int(snapshot.get("extra_lives", self._extra_lives))
        self._active_orb_timer = float(snapshot.get("active_orb_timer", self._active_orb_timer))
        self._active_orb_indefinite = bool(
            snapshot.get("active_orb_indefinite", self._active_orb_indefinite)
        )
        self._active_orb_duration = float(
            snapshot.get("active_orb_duration", self._active_orb_duration)
        )

        facing = snapshot.get("facing", self.facing)
        state = snapshot.get("state", self.state)
        if state in self.animations and facing in self.animations[state]:
            self._set_state(state, facing)
        else:
            self.facing = facing
            self.state = state

        self.rect.center = (round(self.position.x), round(self.position.y))

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
            displacement = move_vector * (self.speed * self._speed_multiplier()) * dt
            
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
        self._power_alpha = 255
        self._death_fade_alpha = 255
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

    def _draw_shield_overlay(self, surface: pygame.Surface, draw_rect: pygame.Rect, opacity_scale: float = 1.0):
        warn = self._shield_timer <= self._shield_warning_threshold
        base_color = (70, 200, 240) if not warn else (230, 180, 90)
        texture = _get_shield_effect_surface()
        if texture:
            max_dim = max(draw_rect.width, draw_rect.height)
            pulse = 0.98 + 0.02 * math.sin(self._status_flash_timer * 4.0)
            target = int((max_dim + 20) * pulse)
            target = max(10, target)
            scaled = pygame.transform.smoothscale(texture, (target, target))
            angle = (self._status_flash_timer * 50.0) % 360
            rotated = pygame.transform.rotozoom(scaled, angle, 1.0)
            effect = rotated.copy()
            tint = pygame.Surface(effect.get_size(), pygame.SRCALPHA)
            tint.fill((*base_color, 255))
            effect.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            alpha = 190 if not warn else 150
            alpha = int(alpha * opacity_scale)
            effect.set_alpha(alpha)
            effect_rect = effect.get_rect(center=draw_rect.center)
            surface.blit(effect, effect_rect)
            return

        radius = max(draw_rect.width, draw_rect.height) // 2 + 8
        pulse = (int(self._status_flash_timer * 8) % 2 == 0)
        alpha = 40 if not warn else (20 if pulse else 70)
        alpha = int(alpha * opacity_scale)
        shield_surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(shield_surf, (*base_color, alpha), (radius + 2, radius + 2), radius, 4)
        surface.blit(shield_surf, (draw_rect.centerx - radius - 2, draw_rect.centery - radius - 2))

    def _has_speed_orb_glow(self) -> bool:
        if self.state == "death":
            return False

        if self._orb_speed_boost > 1.01:
            return True

        if self._active_orb_label != "Speed Boost":
            return False

        return self._active_orb_indefinite or self._active_orb_timer > 0.0

    def _has_void_walk_wings(self) -> bool:
        if self.state == "death":
            return False

        if self.has_void_walk():
            return True

        if self._active_orb_label != "Void Walk":
            return False

        return self._active_orb_indefinite or self._active_orb_timer > 0.0

    def _void_walk_wing_blits(self, draw_rect: pygame.Rect, opacity_scale: float = 1.0):
        alpha = max(0, min(255, int(255 * opacity_scale)))
        if alpha <= 0:
            return [], []

        wing_size = int(max(draw_rect.width, draw_rect.height) * 0.55)
        wing_size = max(18, min(72, wing_size))
        frames = _get_void_walk_wing_frames(wing_size)
        if frames is None:
            return [], []

        left_light, right_light, left_dark, right_dark = frames
        frame_idx = int(self._status_flash_timer * 10.0) % 2

        # For side-facing sprites, tint the far wing to help it read as "behind" the body.
        if self.facing == "left":
            left = left_light[frame_idx]
            right = right_dark[frame_idx]
        elif self.facing == "right":
            left = left_dark[frame_idx]
            right = right_light[frame_idx]
        else:
            left = left_dark[frame_idx]
            right = right_light[frame_idx]

        # Fold the wings so they cling to the player's back (angel-like).
        openness = 0.5 + 0.5 * math.sin(self._status_flash_timer * 6.2)
        openness = 0.20 + 0.80 * openness  # 0.20..1.00
        angle = 30.0 - 14.0 * openness     # ~16..30 degrees
        scale = 0.78 + 0.08 * openness
        squash = 0.78 + 0.12 * openness    # keep wings visible while tucked

        try:
            left = pygame.transform.rotozoom(left, angle, scale)
            right = pygame.transform.rotozoom(right, -angle, scale)

            # Squash width to look like the wings are tucked against the back (but still readable).
            lw, lh = left.get_size()
            rw, rh = right.get_size()
            left = pygame.transform.smoothscale(left, (max(1, int(lw * squash)), lh))
            right = pygame.transform.smoothscale(right, (max(1, int(rw * squash)), rh))
        except Exception:
            pass

        if alpha != 255:
            left = left.copy()
            right = right.copy()
            left.set_alpha(alpha)
            right.set_alpha(alpha)

        # Anchor at upper-back / shoulders (close to spine), using the visible-pixels bounds
        # so direction sprites with extra padding still line up.
        body = None
        try:
            body = self.current_animation.image.get_bounding_rect(min_alpha=10)
        except Exception:
            body = None
        if not body or body.width <= 0 or body.height <= 0:
            body = pygame.Rect(0, 0, draw_rect.width, draw_rect.height)

        anchor_x = draw_rect.left + body.centerx
        anchor_y = draw_rect.top + body.top + int(body.height * 0.36)
        spine_offset = max(2, int(body.width * 0.06))

        # When running sideways, shift the wings toward the back of the sprite so they don't
        # "float" around the midline.
        if self.facing in ("left", "right"):
            back_shift = max(0, int(body.width * 0.08))
            anchor_x += back_shift if self.facing == "left" else -back_shift

        left_rect = left.get_rect(center=(anchor_x - spine_offset, anchor_y))
        right_rect = right.get_rect(center=(anchor_x + spine_offset, anchor_y))

        if self.facing == "left":
            return [(right, right_rect.topleft)], [(left, left_rect.topleft)]
        if self.facing == "right":
            return [(left, left_rect.topleft)], [(right, right_rect.topleft)]
        return [(left, left_rect.topleft), (right, right_rect.topleft)], []

    def _draw_speed_orb_glow(self, surface: pygame.Surface, draw_rect: pygame.Rect, opacity_scale: float = 1.0):
        """Draw a yellow shimmering aura around the player's collision silhouette."""
        self._refresh_collision_shape()
        pulse = 0.5 + 0.5 * math.sin(self._status_flash_timer * 10.0)
        glow_pad = 16

        if len(self._collision_outline) >= 2:
            glow_size = (draw_rect.width + glow_pad * 2, draw_rect.height + glow_pad * 2)
            glow = pygame.Surface(glow_size, pygame.SRCALPHA)
            points = [(x + glow_pad, y + glow_pad) for x, y in self._collision_outline]

            outer_alpha = int((30 + 50 * pulse) * opacity_scale)
            mid_alpha = int((70 + 90 * pulse) * opacity_scale)
            inner_alpha = int((140 + 90 * pulse) * opacity_scale)

            pygame.draw.lines(glow, (255, 215, 40, outer_alpha), True, points, 8)
            pygame.draw.lines(glow, (255, 235, 95, mid_alpha), True, points, 4)
            pygame.draw.lines(glow, (255, 255, 185, inner_alpha), True, points, 2)

            step = max(1, len(points) // 10)
            sparkle_alpha = int((130 + 90 * (1.0 - pulse)) * opacity_scale)
            for idx in range(0, len(points), step):
                x, y = points[idx]
                pygame.draw.circle(glow, (255, 245, 155, sparkle_alpha), (x, y), 2)

            surface.blit(glow, (draw_rect.left - glow_pad, draw_rect.top - glow_pad))
            return

        fallback = pygame.Surface((draw_rect.width + 36, draw_rect.height + 36), pygame.SRCALPHA)
        f_rect = fallback.get_rect()
        outer_alpha = int((40 + 60 * pulse) * opacity_scale)
        inner_alpha = int((120 + 80 * pulse) * opacity_scale)
        pygame.draw.ellipse(fallback, (255, 215, 60, outer_alpha), f_rect, 6)
        pygame.draw.ellipse(fallback, (255, 255, 180, inner_alpha), f_rect.inflate(-10, -10), 3)
        surface.blit(fallback, (draw_rect.left - 18, draw_rect.top - 18))

    def _draw_freeze_overlay(self, surface: pygame.Surface, draw_rect: pygame.Rect, opacity_scale: float = 1.0):
        self._refresh_collision_shape()
        if len(self._collision_outline) < 2:
            return

        frost = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
        pulse = 0.5 + 0.5 * math.sin(self._status_flash_timer * 8.0)
        line_alpha = int((90 + 75 * pulse) * opacity_scale)
        spark_alpha = int((150 + 70 * (1.0 - pulse)) * opacity_scale)

        outline_points = self._collision_outline
        pygame.draw.lines(frost, (150, 200, 255, line_alpha), True, outline_points, 2)
        pygame.draw.lines(frost, (245, 250, 255, int(line_alpha * 0.65)), True, outline_points, 1)

        step = max(1, len(outline_points) // 8)
        for idx in range(0, len(outline_points), step):
            x, y = outline_points[idx]
            radius = 2 + ((idx // step) % 2)
            pygame.draw.circle(frost, (225, 245, 255, spark_alpha), (x, y), radius)

        surface.blit(frost, draw_rect.topleft)

    def _draw_power_orb_icons(self, surface: pygame.Surface):
        spacing = 14
        total = POWER_ORBS_REQUIRED
        start_x = self.rect.centerx - ((total - 1) * spacing) / 2
        y = self.rect.top - 14
        for idx in range(total):
            cx = int(start_x + idx * spacing)
            cy = int(y)
            filled = idx < self.power_orb_charges
            color = (200, 80, 255) if filled else (90, 60, 120)
            pygame.draw.circle(surface, color, (cx, cy), 4)
            pygame.draw.circle(surface, (255, 255, 255), (cx, cy), 4, 1)
