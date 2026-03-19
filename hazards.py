"""
Hazard system for Grid Survival.
Implements bullets and moving traps that threaten players.
"""

import random
import pygame
from typing import List, Tuple, Optional

from collision_manager import CollisionManager
from settings import WINDOW_SIZE


class Bullet:
    """Projectile hazard that moves in a straight line."""
    
    def __init__(self, position: Tuple[float, float], direction: pygame.Vector2, speed: float = 300):
        self.position = pygame.Vector2(position)
        self.direction = direction.normalize() if direction.length() > 0 else pygame.Vector2(1, 0)
        self.speed = speed
        self.radius = 8
        self.color = (255, 50, 50)
        self.active = True
    
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
    
    def check_collision(self, player_rect: pygame.Rect) -> bool:
        """Check if bullet hits player."""
        if not self.active:
            return False
        return self.get_rect().colliderect(player_rect)


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
    
    def check_collision(self, player_rect: pygame.Rect) -> bool:
        """Check if trap hits player."""
        if not self.active:
            return False
        return self.get_rect().colliderect(player_rect)


class HazardManager:
    """Manages all hazards in the game with difficulty scaling."""
    
    def __init__(self, collision_manager: Optional[CollisionManager] = None):
        self.bullets: List[Bullet] = []
        self.traps: List[MovingTrap] = []
        self.time_elapsed = 0.0
        self.bullet_spawn_timer = 0.0
        self.trap_spawn_timer = 0.0
        
        # Difficulty scaling
        self.bullet_spawn_interval = 3.0  # seconds
        self.trap_spawn_interval = 8.0  # seconds
        self.min_bullet_interval = 1.0
        self.min_trap_interval = 5.0
        self.difficulty_scale_rate = 0.98
        
        # Hazard activation threshold
        self.hazard_start_time = 15.0  # Start spawning after 15 seconds
        self.collision_manager = collision_manager
    
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
    
    def check_player_collision(self, player) -> bool:
        """Check if any hazard hits the player."""
        for bullet in self.bullets:
            if self.collision_manager:
                if self.collision_manager.bullet_hits_player(bullet, player):
                    return True
            else:
                if bullet.check_collision(player.rect):
                    bullet.active = False
                    return True
        
        for trap in self.traps:
            if trap.check_collision(player.rect):
                return True
        
        return False
    
    def reset(self):
        """Reset all hazards."""
        self.bullets.clear()
        self.traps.clear()
        self.time_elapsed = 0.0
        self.bullet_spawn_timer = 0.0
        self.trap_spawn_timer = 0.0
        self.bullet_spawn_interval = 3.0
        self.trap_spawn_interval = 8.0
        if self.collision_manager:
            self.collision_manager.reset_caches()
