"""
Hazard system for Grid Survival.
Implements bullets, animated hazards (snakes, spiders), and moving traps that threaten players.
"""

import random
import math
import pygame
from typing import List, Tuple, Optional

from audio import get_audio
from collision_manager import CollisionManager
from settings import ASSETS_DIR, WINDOW_SIZE


HAZARD_ASSETS_DIR = ASSETS_DIR / "Hazards"


class AnimatedHazard:
    """Animated hazard (snake, spider, etc.) with sprite animation."""
    
    HAZARD_CONFIGS = {
        "snake": {
            "scale": 0.3,
            "speed": 80,
            "damage": 1,
            "animation_dirs": ["idle", "move"],
            "color": (80, 180, 60),
        },
        "spider": {
            "scale": 0.35,
            "speed": 60,
            "damage": 1,
            "animation_dirs": ["idle", "move"],
            "color": (40, 40, 40),
        },
        "scorpion": {
            "scale": 0.4,
            "speed": 70,
            "damage": 2,
            "animation_dirs": ["idle", "move"],
            "color": (160, 80, 20),
        },
        "bat": {
            "scale": 0.25,
            "speed": 120,
            "damage": 1,
            "animation_dirs": ["idle", "move"],
            "color": (80, 60, 80),
        },
    }
    
    def __init__(self, hazard_type: str, position: Tuple[float, float], patrol_points: Optional[List[Tuple[float, float]]] = None):
        self.hazard_type = hazard_type
        self.position = pygame.Vector2(position)
        self.patrol_points = patrol_points or []
        self.current_patrol_index = 0
        self.patrol_direction = 1
        
        config = self.HAZARD_CONFIGS.get(hazard_type, self.HAZARD_CONFIGS["snake"])
        self.speed = config["speed"]
        self.damage = config["damage"]
        self.color = config["color"]
        self.scale = config["scale"]
        
        self.active = True
        self.facing = "right"
        
        self.animation_frames: dict = {}
        self.current_anim = "idle"
        self.frame_index = 0
        self.frame_timer = 0.0
        self.frame_duration = 0.15
        
        self._load_assets()
    
    def _load_assets(self):
        """Load hazard assets - try sprite sheets first, then folder, or use procedural fallback."""
        loaded = False
        
        sprite_sheet_map = {
            "snake": "Snake sprite sheet.png",
            "spider": "DungeonSpider.png",
        }
        
        sheet_name = sprite_sheet_map.get(self.hazard_type)
        if sheet_name:
            sheet_path = HAZARD_ASSETS_DIR / sheet_name
            if sheet_path.exists():
                try:
                    sheet = pygame.image.load(sheet_path.as_posix()).convert_alpha()
                    sheet_width, sheet_height = sheet.get_size()
                    
                    if self.hazard_type == "snake":
                        frame_width = sheet_width // 4
                        frame_height = sheet_height // 2
                        for row, anim_name in enumerate(["idle", "move"]):
                            frames = []
                            for col in range(4):
                                rect = pygame.Rect(col * frame_width, row * frame_height, frame_width, frame_height)
                                frame = pygame.Surface(rect.size, pygame.SRCALPHA)
                                frame.blit(sheet, (0, 0), rect)
                                new_size = (int(frame_width * self.scale), int(frame_height * self.scale))
                                frame = pygame.transform.smoothscale(frame, new_size)
                                frames.append(frame)
                            if frames:
                                self.animation_frames[anim_name] = frames
                        loaded = True
                    
                    elif self.hazard_type == "spider":
                        frame_width = sheet_width // 4
                        frame_height = sheet_height // 2
                        for row, anim_name in enumerate(["idle", "move"]):
                            frames = []
                            for col in range(4):
                                rect = pygame.Rect(col * frame_width, row * frame_height, frame_width, frame_height)
                                frame = pygame.Surface(rect.size, pygame.SRCALPHA)
                                frame.blit(sheet, (0, 0), rect)
                                new_size = (int(frame_width * self.scale), int(frame_height * self.scale))
                                frame = pygame.transform.smoothscale(frame, new_size)
                                frames.append(frame)
                            if frames:
                                self.animation_frames[anim_name] = frames
                        loaded = True
                except Exception as e:
                    print(f"Failed to load sprite sheet for {self.hazard_type}: {e}")
        
        if not loaded:
            hazard_dir = HAZARD_ASSETS_DIR / self.hazard_type
            if not hazard_dir.exists():
                self._create_procedural_frames()
                return
            
            for anim_name in self.HAZARD_CONFIGS.get(self.hazard_type, {}).get("animation_dirs", ["idle", "move"]):
                anim_dir = hazard_dir / anim_name
                if anim_dir.exists():
                    frames = []
                    for frame_file in sorted(anim_dir.glob("*.png")):
                        try:
                            frame = pygame.image.load(frame_file.as_posix()).convert_alpha()
                            w, h = frame.get_size()
                            new_size = (int(w * self.scale), int(h * self.scale))
                            frame = pygame.transform.smoothscale(frame, new_size)
                            frames.append(frame)
                        except Exception:
                            continue
                    if frames:
                        self.animation_frames[anim_name] = frames
            
            if not self.animation_frames:
                self._create_procedural_frames()
    
    def _create_procedural_frames(self):
        """Create procedural animation frames when no assets exist."""
        base_size = 64
        frames_idle = []
        frames_move = []
        
        for i in range(4):
            surf = pygame.Surface((base_size, base_size), pygame.SRCALPHA)
            
            if self.hazard_type == "snake":
                body_color = self.color
                head_color = (self.color[0] + 40, self.color[1] + 40, self.color[2])
                center = base_size // 2
                offset = math.sin(i * math.pi / 2) * 3
                pygame.draw.ellipse(surf, body_color, (10, center - 8 + offset, 44, 16))
                pygame.draw.ellipse(surf, body_color, (20, center - 12 + offset, 30, 24))
                pygame.draw.circle(surf, head_color, (base_size - 12, center + offset), 10)
                eye_color = (255, 255, 0)
                pygame.draw.circle(surf, eye_color, (base_size - 8, center - 2 + offset), 3)
                pygame.draw.circle(surf, eye_color, (base_size - 16, center - 2 + offset), 3)
                if i % 2 == 0:
                    tongue_color = (200, 50, 50)
                    pygame.draw.line(surf, tongue_color, (base_size - 2, center + offset), (base_size + 8, center + offset), 2)
            
            elif self.hazard_type == "spider":
                body_color = self.color
                leg_color = (self.color[0] + 30, self.color[1] + 30, self.color[2] + 30)
                center = base_size // 2
                leg_offset = math.sin(i * math.pi / 2) * 4
                pygame.draw.ellipse(surf, body_color, (24, center - 12, 16, 24))
                pygame.draw.circle(surf, body_color, (center, center - 6), 12)
                leg_pairs = [(-1, -20), (-1, 20), (1, -20), (1, 20)]
                for side, y_off in leg_pairs:
                    for j in range(3):
                        start = (center + side * 8, center - 10 + j * 8)
                        end = (center + side * (24 + j * 4 + leg_offset), center - 20 + j * 12)
                        pygame.draw.line(surf, leg_color, start, end, 2)
                pygame.draw.circle(surf, (255, 0, 0), (center - 3, center - 8), 2)
                pygame.draw.circle(surf, (255, 0, 0), (center + 3, center - 8), 2)
            
            elif self.hazard_type == "scorpion":
                body_color = self.color
                tail_color = (self.color[0] + 20, self.color[1] - 20, self.color[2] - 20)
                center = base_size // 2
                tail_curve = i * 8
                pygame.draw.ellipse(surf, body_color, (16, center - 10, 32, 20))
                for seg in range(5):
                    x = base_size - 8 - seg * 6
                    y = center - 8 - seg * 2 + (2 if seg < 2 else tail_curve // 4)
                    pygame.draw.circle(surf, tail_color, (x, y), 6 - seg)
                pincer_offset = math.sin(i * math.pi / 2) * 3
                pygame.draw.ellipse(surf, (200, 150, 100), (8, center - 20 + pincer_offset, 12, 8))
                pygame.draw.ellipse(surf, (200, 150, 100), (8, center + 12 + pincer_offset, 12, 8))
                pygame.draw.circle(surf, (255, 255, 255), (30, center - 4), 2)
                pygame.draw.circle(surf, (255, 255, 255), (36, center - 4), 2)
            
            elif self.hazard_type == "bat":
                body_color = self.color
                wing_color = (self.color[0] - 20, self.color[1] - 20, self.color[2] - 20)
                center = base_size // 2
                wing_fold = i % 2 * 8
                pygame.draw.circle(surf, body_color, (center, center), 10)
                for side in [-1, 1]:
                    wing_points = [
                        (center + side * 8, center - 4),
                        (center + side * (24 + wing_fold), center - 8 - (i % 2) * 4),
                        (center + side * (20 + wing_fold), center + 4 + (i % 2) * 4),
                        (center + side * 8, center + 4),
                    ]
                    pygame.draw.polygon(surf, wing_color, wing_points)
                eye_color = (255, 100, 100)
                pygame.draw.circle(surf, eye_color, (center - 3, center - 2), 2)
                pygame.draw.circle(surf, eye_color, (center + 3, center - 2), 2)
            
            new_size = (int(base_size * self.scale), int(base_size * self.scale))
            surf = pygame.transform.smoothscale(surf, new_size)
            frames_idle.append(surf)
            frames_move.append(surf)
        
        self.animation_frames = {"idle": frames_idle, "move": frames_move}
    
    def update(self, dt: float):
        """Update hazard position and animation."""
        if not self.active:
            return
        
        if self.patrol_points:
            self._update_patrol(dt)
        
        self.frame_timer += dt
        if self.frame_timer >= self.frame_duration:
            self.frame_timer = 0
            frames = self.animation_frames.get(self.current_anim, self.animation_frames.get("idle", []))
            if frames:
                self.frame_index = (self.frame_index + 1) % len(frames)
    
    def _update_patrol(self, dt: float):
        """Move between patrol points."""
        if len(self.patrol_points) < 2:
            return
        
        target = pygame.Vector2(self.patrol_points[self.current_patrol_index])
        direction = target - self.position
        distance = direction.length()
        
        if distance < 5:
            self.current_patrol_index += self.patrol_direction
            if self.current_patrol_index >= len(self.patrol_points):
                self.current_patrol_index = max(0, len(self.patrol_points) - 2)
                self.patrol_direction = -1
            elif self.current_patrol_index < 0:
                self.current_patrol_index = min(1, len(self.patrol_points) - 1)
                self.patrol_direction = 1
            self.current_anim = "idle"
        else:
            direction = direction.normalize()
            self.position += direction * self.speed * dt
            self.current_anim = "move"
            if direction.x > 0:
                self.facing = "right"
            elif direction.x < 0:
                self.facing = "left"
    
    def draw(self, surface: pygame.Surface):
        """Draw hazard with animation."""
        if not self.active:
            return
        
        frames = self.animation_frames.get(self.current_anim, self.animation_frames.get("idle", []))
        if not frames:
            return
        
        frame = frames[self.frame_index % len(frames)]
        
        if self.facing == "left":
            frame = pygame.transform.flip(frame, True, False)
        
        rect = frame.get_rect(center=(int(self.position.x), int(self.position.y)))
        surface.blit(frame, rect)
    
    def get_rect(self) -> pygame.Rect:
        """Get collision rect."""
        size = int(32 * self.scale)
        return pygame.Rect(
            int(self.position.x - size // 2),
            int(self.position.y - size // 2),
            size,
            size
        )
    
    def check_collision(self, player) -> bool:
        """Check if hazard hits player."""
        if not self.active:
            return False
        hitbox = player.get_hitbox() if hasattr(player, 'get_hitbox') else player.rect
        return self.get_rect().colliderect(hitbox)
    
    def snapshot_state(self) -> dict:
        """Serialize hazard state for network sync."""
        return {
            "type": self.hazard_type,
            "x": float(self.position.x),
            "y": float(self.position.y),
            "patrol_points": self.patrol_points,
            "current_patrol_index": self.current_patrol_index,
            "patrol_direction": self.patrol_direction,
            "active": self.active,
            "current_anim": self.current_anim,
            "frame_index": self.frame_index,
        }
    
    @classmethod
    def from_snapshot(cls, snapshot: dict) -> "AnimatedHazard":
        """Create hazard from snapshot."""
        hazard_type = snapshot.get("type", "snake")
        position = (snapshot.get("x", 0), snapshot.get("y", 0))
        patrol_points = snapshot.get("patrol_points", [])
        hazard = cls(hazard_type, position, patrol_points)
        hazard.current_patrol_index = snapshot.get("current_patrol_index", 0)
        hazard.patrol_direction = snapshot.get("patrol_direction", 1)
        hazard.active = snapshot.get("active", True)
        hazard.current_anim = snapshot.get("current_anim", "idle")
        hazard.frame_index = snapshot.get("frame_index", 0)
        return hazard


class Bullet:
    """Projectile hazard that moves in a straight line."""
    
    def __init__(self, position: Tuple[float, float], direction: pygame.Vector2, speed: float = 300):
        self.position = pygame.Vector2(position)
        self.direction = direction.normalize() if direction.length() > 0 else pygame.Vector2(1, 0)
        self.speed = speed
        self.radius = 8
        self.color = (255, 50, 50)
        self.active = True
        self.damage = 1
        self.owner = None
        self.is_fireball = False
    
    def update(self, dt: float):
        """Update bullet position."""
        self.position += self.direction * self.speed * dt
        
        # Deactivate if off screen
        if (self.position.x < -50 or self.position.x > WINDOW_SIZE[0] + 50 or
            self.position.y < -50 or self.position.y > WINDOW_SIZE[1] + 50):
            self.active = False
    
    def draw(self, surface: pygame.Surface):
        """Draw bullet."""
        if self.active:
            pygame.draw.circle(surface, self.color, (int(self.position.x), int(self.position.y)), self.radius)
            # Draw trail effect
            trail_color = (255, 100, 100, 128)
            trail_pos = self.position - self.direction * 15
            pygame.draw.circle(surface, trail_color, (int(trail_pos.x), int(trail_pos.y)), self.radius // 2)
    
    def get_rect(self) -> pygame.Rect:
        """Get collision rect."""
        return pygame.Rect(
            int(self.position.x - self.radius),
            int(self.position.y - self.radius),
            self.radius * 2,
            self.radius * 2
        )
    
    def check_collision(self, player) -> bool:
        """Check if bullet hits player."""
        if not self.active:
            return False
        # Use player's tighter hitbox if available
        hitbox = player.get_hitbox() if hasattr(player, 'get_hitbox') else player.rect
        return self.get_rect().colliderect(hitbox)


class MovingTrap:
    """Moving hazard that patrols between two points."""
    
    def __init__(self, start_pos: Tuple[float, float], end_pos: Tuple[float, float], speed: float = 150):
        self.start_pos = pygame.Vector2(start_pos)
        self.end_pos = pygame.Vector2(end_pos)
        self.position = pygame.Vector2(start_pos)
        self.speed = speed
        self.size = 32
        self.color = (200, 50, 200)
        self.active = True
        self.moving_to_end = True
        self.direction = (self.end_pos - self.start_pos).normalize() if (self.end_pos - self.start_pos).length() > 0 else pygame.Vector2(1, 0)
    
    def update(self, dt: float):
        """Update trap position."""
        if self.moving_to_end:
            self.position += self.direction * self.speed * dt
            if self.position.distance_to(self.end_pos) < 5:
                self.moving_to_end = False
                self.direction = (self.start_pos - self.end_pos).normalize()
        else:
            self.position += self.direction * self.speed * dt
            if self.position.distance_to(self.start_pos) < 5:
                self.moving_to_end = True
                self.direction = (self.end_pos - self.start_pos).normalize()
    
    def draw(self, surface: pygame.Surface):
        """Draw trap."""
        if self.active:
            rect = pygame.Rect(
                int(self.position.x - self.size // 2),
                int(self.position.y - self.size // 2),
                self.size,
                self.size
            )
            pygame.draw.rect(surface, self.color, rect)
            pygame.draw.rect(surface, (255, 100, 255), rect, 3)
            # Draw spikes
            points = [
                (rect.centerx, rect.top),
                (rect.left, rect.centery),
                (rect.centerx, rect.bottom),
                (rect.right, rect.centery)
            ]
            for point in points:
                pygame.draw.circle(surface, (255, 255, 0), point, 4)
    
    def get_rect(self) -> pygame.Rect:
        """Get collision rect."""
        return pygame.Rect(
            int(self.position.x - self.size // 2),
            int(self.position.y - self.size // 2),
            self.size,
            self.size
        )
    
    def check_collision(self, player) -> bool:
        """Check if trap hits player."""
        if not self.active:
            return False
        # Use player's tighter hitbox if available
        hitbox = player.get_hitbox() if hasattr(player, 'get_hitbox') else player.rect
        return self.get_rect().colliderect(hitbox)


class Explosion:
    """Particle explosion effect with punchy visuals."""
    
    def __init__(self, position: Tuple[float, float], color: Tuple[int, int, int] = (255, 100, 50)):
        self.particles: List[dict] = []
        self.position = pygame.Vector2(position)
        self.ring_radius = 5.0
        self.ring_alpha = 255.0
        self.active = True
        
        colors = [
            (255, 50, 50),   # Red
            (255, 140, 0),   # Orange
            (255, 255, 100), # Yellow
            (100, 100, 100)  # Smoke Grey
        ]
        
        for _ in range(40):
            angle = random.uniform(0, 360) 
            speed = random.uniform(150, 450)  # Much faster initial burst
            rad = math.radians(angle)
            velocity = pygame.Vector2(math.cos(rad), math.sin(rad)) * speed
            
            self.particles.append({
                'pos': pygame.Vector2(position),
                'vel': velocity,
                'radius': random.uniform(4, 10),
                'life': 1.0,
                'max_life': 1.0,
                'decay': random.uniform(1.5, 4.0),
                'color': random.choice(colors),
                'drag': random.uniform(0.01, 0.1)  # Very strong drag
            })

    def update(self, dt: float) -> bool:
        """Update particles. Returns True if explosion is still active."""
        particle_active = False
        
        # Expand ring faster
        if self.ring_alpha > 0:
            self.ring_radius += 600 * dt
            self.ring_alpha -= 900 * dt
            if self.ring_alpha < 0:
                self.ring_alpha = 0
            
        for p in self.particles:
            p['life'] -= dt * p['decay']
            if p['life'] > 0:
                # Strong drag effect: slow down rapidly
                p['vel'] *= math.pow(p['drag'], dt)
                p['pos'] += p['vel'] * dt
                particle_active = True
        
        return particle_active or self.ring_alpha > 0

    def draw(self, surface: pygame.Surface):
        # Draw expanding ring (shockwave)
        if self.ring_alpha > 0:
             # Draw a white circle with alpha
            surf = pygame.Surface((int(self.ring_radius * 2) + 2, int(self.ring_radius * 2) + 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (255, 255, 255, int(self.ring_alpha)), 
                             (int(self.ring_radius), int(self.ring_radius)), int(self.ring_radius), 3)
            surface.blit(surf, (self.position.x - self.ring_radius, self.position.y - self.ring_radius))

        # Draw particles
        for p in self.particles:
            if p['life'] > 0:
                # Fade out size and alpha
                life_ratio = p['life'] / p['max_life']
                radius = int(p['radius'] * life_ratio)
                if radius > 1:
                    pygame.draw.circle(surface, p['color'], (int(p['pos'].x), int(p['pos'].y)), radius)


class HazardManager:
    """Manages all hazards in the game with difficulty scaling."""
    
    def __init__(self, collision_manager: Optional[CollisionManager] = None):
        self.bullets: List[Bullet] = []
        self.traps: List[MovingTrap] = []
        self.explosions: List[Explosion] = []
        self.animated_hazards: List[AnimatedHazard] = []
        self.time_elapsed = 0.0
        self.bullet_spawn_timer = 0.0
        self.trap_spawn_timer = 0.0
        self.hazard_spawn_timer = 0.0
        
        # Difficulty scaling
        self.bullet_spawn_interval = 3.0  # seconds
        self.trap_spawn_interval = 8.0  # seconds
        self.min_bullet_interval = 1.0
        self.min_trap_interval = 5.0
        self.difficulty_scale_rate = 0.98
        
        # Hazard activation threshold
        self.hazard_start_time = 15.0  # Start spawning after 15 seconds
        self.collision_manager = collision_manager

        # Preload explosion sound
        try:
            get_audio().preload_sfx("explosions.mp3")
        except Exception as e:
            print(f"Warning: Could not preload explosion sound: {e}")
    
    def update(self, dt: float):
        """Update all hazards and spawn new ones."""
        self.time_elapsed += dt
        
        # Only spawn hazards after threshold time
        if self.time_elapsed < self.hazard_start_time:
            return
        
        # Update existing hazards
        for bullet in self.bullets[:]:
            bullet.update(dt)
            if not bullet.active:
                self.bullets.remove(bullet)
        
        for trap in self.traps:
            trap.update(dt)
        
        for hazard in self.animated_hazards:
            hazard.update(dt)

        # Update explosions
        self.explosions = [e for e in self.explosions if e.update(dt)]
        
        # Spawn new bullets
        self.bullet_spawn_timer += dt
        if self.bullet_spawn_timer >= self.bullet_spawn_interval:
            self.bullet_spawn_timer = 0.0
            self._spawn_bullet()
            # Increase difficulty
            self.bullet_spawn_interval = max(
                self.min_bullet_interval,
                self.bullet_spawn_interval * self.difficulty_scale_rate
            )
        
        # Spawn new traps
        self.trap_spawn_timer += dt
        if self.trap_spawn_timer >= self.trap_spawn_interval and len(self.traps) < 4:
            self.trap_spawn_timer = 0.0
            self._spawn_trap()
            # Increase difficulty
            self.trap_spawn_interval = max(
                self.min_trap_interval,
                self.trap_spawn_interval * self.difficulty_scale_rate
            )
        
        # Spawn animated hazards (snakes, spiders, etc)
        self.hazard_spawn_timer += dt
        if self.hazard_spawn_timer >= 12.0 and len(self.animated_hazards) < 3:
            self.hazard_spawn_timer = 0.0
            self._spawn_animated_hazard()
    
    def _spawn_animated_hazard(self):
        """Spawn an animated hazard (snake, spider, etc)."""
        hazard_types = list(AnimatedHazard.HAZARD_CONFIGS.keys())
        hazard_type = random.choice(hazard_types)
        
        margin = 100
        start_x = random.randint(margin, WINDOW_SIZE[0] - margin)
        start_y = random.randint(margin, WINDOW_SIZE[1] - margin)
        
        offset_x = random.randint(-150, 150)
        offset_y = random.randint(-150, 150)
        end_x = max(margin, min(WINDOW_SIZE[0] - margin, start_x + offset_x))
        end_y = max(margin, min(WINDOW_SIZE[1] - margin, start_y + offset_y))
        
        patrol_points = [(float(start_x), float(start_y)), (float(end_x), float(end_y))]
        self.animated_hazards.append(AnimatedHazard(hazard_type, (start_x, start_y), patrol_points))
    
    def _spawn_bullet(self):
        """Spawn a bullet from a random edge."""
        edge = random.choice(['top', 'bottom', 'left', 'right'])
        
        if edge == 'top':
            pos = (random.randint(50, WINDOW_SIZE[0] - 50), -20)
            direction = pygame.Vector2(random.uniform(-0.5, 0.5), 1)
        elif edge == 'bottom':
            pos = (random.randint(50, WINDOW_SIZE[0] - 50), WINDOW_SIZE[1] + 20)
            direction = pygame.Vector2(random.uniform(-0.5, 0.5), -1)
        elif edge == 'left':
            pos = (-20, random.randint(50, WINDOW_SIZE[1] - 50))
            direction = pygame.Vector2(1, random.uniform(-0.5, 0.5))
        else:  # right
            pos = (WINDOW_SIZE[0] + 20, random.randint(50, WINDOW_SIZE[1] - 50))
            direction = pygame.Vector2(-1, random.uniform(-0.5, 0.5))
        
        self.bullets.append(Bullet(pos, direction))
    
    def _spawn_trap(self):
        """Spawn a moving trap with random patrol path."""
        # Create patrol path within playable area
        margin = 100
        start_x = random.randint(margin, WINDOW_SIZE[0] - margin)
        start_y = random.randint(margin, WINDOW_SIZE[1] - margin)
        
        # End point is offset from start
        offset_x = random.randint(-200, 200)
        offset_y = random.randint(-200, 200)
        end_x = max(margin, min(WINDOW_SIZE[0] - margin, start_x + offset_x))
        end_y = max(margin, min(WINDOW_SIZE[1] - margin, start_y + offset_y))
        
        self.traps.append(MovingTrap((start_x, start_y), (end_x, end_y)))
    
    def draw(self, surface: pygame.Surface):
        """Draw all hazards."""
        for bullet in self.bullets:
            bullet.draw(surface)
        for trap in self.traps:
            trap.draw(surface)
        for hazard in self.animated_hazards:
            hazard.draw(surface)
        for explosion in self.explosions:
            explosion.draw(surface)
    
    def check_player_collision(self, player) -> bool:
        """Check if any hazard hits the player."""
        if getattr(player, "_immune_to_hazards", False):
            return False

        hit = False
        
        for bullet in self.bullets:
            bullet_hit = False
            if self.collision_manager:
                if self.collision_manager.bullet_hits_player(bullet, player):
                    bullet_hit = True
            else:
                if bullet.check_collision(player):
                    bullet_hit = True
            
            if bullet_hit:
                bullet.active = False
                self.explosions.append(Explosion((bullet.position.x, bullet.position.y), bullet.color))
                get_audio().play_sfx("explosions.mp3")
                hit = True
        
        for trap in self.traps:
            if trap.check_collision(player):
                self.explosions.append(Explosion((trap.position.x, trap.position.y), trap.color))
                get_audio().play_sfx("explosions.mp3")
                hit = True
        
        for hazard in self.animated_hazards:
            if hazard.check_collision(player):
                self.explosions.append(Explosion((hazard.position.x, hazard.position.y), hazard.color))
                get_audio().play_sfx("explosions.mp3")
                hit = True
        
        return hit
    
    def is_position_safe(self, position, radius: float = 24) -> bool:
        """Return True if no active hazard overlaps the given point."""
        rect = pygame.Rect(0, 0, int(radius * 2), int(radius * 2))
        rect.center = (int(position[0]), int(position[1]))

        for bullet in self.bullets:
            if bullet.active and rect.colliderect(bullet.get_rect()):
                return False

        for trap in self.traps:
            if rect.colliderect(trap.get_rect()):
                return False
        
        for hazard in self.animated_hazards:
            if hazard.active and rect.colliderect(hazard.get_rect()):
                return False

        return True

    def reset(self):
        """Reset all hazards."""
        self.bullets.clear()
        self.traps.clear()
        self.animated_hazards.clear()
        self.explosions.clear()
        self.time_elapsed = 0.0
        self.bullet_spawn_timer = 0.0
        self.trap_spawn_timer = 0.0
        self.hazard_spawn_timer = 0.0
        self.bullet_spawn_interval = 3.0
        self.trap_spawn_interval = 8.0
        if self.collision_manager:
            self.collision_manager.reset_caches()

    def snapshot_state(self) -> dict:
        """Serialize host hazard state for LAN snapshot sync."""
        return {
            "time_elapsed": float(self.time_elapsed),
            "bullet_spawn_timer": float(self.bullet_spawn_timer),
            "trap_spawn_timer": float(self.trap_spawn_timer),
            "hazard_spawn_timer": float(self.hazard_spawn_timer),
            "bullet_spawn_interval": float(self.bullet_spawn_interval),
            "trap_spawn_interval": float(self.trap_spawn_interval),
            "bullets": [
                {
                    "x": float(bullet.position.x),
                    "y": float(bullet.position.y),
                    "dx": float(bullet.direction.x),
                    "dy": float(bullet.direction.y),
                    "speed": float(bullet.speed),
                    "active": bool(bullet.active),
                }
                for bullet in self.bullets
            ],
            "traps": [
                {
                    "start_x": float(trap.start_pos.x),
                    "start_y": float(trap.start_pos.y),
                    "end_x": float(trap.end_pos.x),
                    "end_y": float(trap.end_pos.y),
                    "x": float(trap.position.x),
                    "y": float(trap.position.y),
                    "speed": float(trap.speed),
                    "moving_to_end": bool(trap.moving_to_end),
                    "dx": float(trap.direction.x),
                    "dy": float(trap.direction.y),
                    "active": bool(trap.active),
                }
                for trap in self.traps
            ],
            "animated_hazards": [h.snapshot_state() for h in self.animated_hazards],
        }

    def apply_snapshot(self, snapshot: dict | None) -> None:
        """Apply a host hazard snapshot on the LAN client."""
        if not isinstance(snapshot, dict):
            return

        self.time_elapsed = float(snapshot.get("time_elapsed", self.time_elapsed))
        self.bullet_spawn_timer = float(
            snapshot.get("bullet_spawn_timer", self.bullet_spawn_timer)
        )
        self.trap_spawn_timer = float(snapshot.get("trap_spawn_timer", self.trap_spawn_timer))
        self.hazard_spawn_timer = float(snapshot.get("hazard_spawn_timer", self.hazard_spawn_timer))
        self.bullet_spawn_interval = float(
            snapshot.get("bullet_spawn_interval", self.bullet_spawn_interval)
        )
        self.trap_spawn_interval = float(
            snapshot.get("trap_spawn_interval", self.trap_spawn_interval)
        )

        self.bullets = []
        for bullet_state in snapshot.get("bullets", []) or []:
            if not isinstance(bullet_state, dict):
                continue
            bullet = Bullet(
                (
                    float(bullet_state.get("x", 0.0)),
                    float(bullet_state.get("y", 0.0)),
                ),
                pygame.Vector2(
                    float(bullet_state.get("dx", 1.0)),
                    float(bullet_state.get("dy", 0.0)),
                ),
                speed=float(bullet_state.get("speed", 300.0)),
            )
            bullet.active = bool(bullet_state.get("active", True))
            self.bullets.append(bullet)

        self.traps = []
        for trap_state in snapshot.get("traps", []) or []:
            if not isinstance(trap_state, dict):
                continue
            trap = MovingTrap(
                (
                    float(trap_state.get("start_x", 0.0)),
                    float(trap_state.get("start_y", 0.0)),
                ),
                (
                    float(trap_state.get("end_x", 0.0)),
                    float(trap_state.get("end_y", 0.0)),
                ),
                speed=float(trap_state.get("speed", 150.0)),
            )
            trap.position = pygame.Vector2(
                float(trap_state.get("x", trap.position.x)),
                float(trap_state.get("y", trap.position.y)),
            )
            trap.moving_to_end = bool(trap_state.get("moving_to_end", trap.moving_to_end))
            trap.direction = pygame.Vector2(
                float(trap_state.get("dx", trap.direction.x)),
                float(trap_state.get("dy", trap.direction.y)),
            )
            trap.active = bool(trap_state.get("active", True))
            self.traps.append(trap)
        
        self.animated_hazards = []
        for hazard_state in snapshot.get("animated_hazards", []) or []:
            if isinstance(hazard_state, dict):
                self.animated_hazards.append(AnimatedHazard.from_snapshot(hazard_state))

        self.explosions.clear()
