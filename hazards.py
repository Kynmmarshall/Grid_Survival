"""
Hazard system for Grid Survival.
Implements bullets and moving traps that threaten players.
"""

import random
import math
import pygame
from typing import List, Tuple, Optional

from audio import get_audio
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
        for explosion in self.explosions:
            explosion.draw(surface)
    
    def check_player_collision(self, player) -> bool:
        """Check if any hazard hits the player."""
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

        return True

    def reset(self):
        """Reset all hazards."""
        self.bullets.clear()
        self.traps.clear()
        self.explosions.clear()
        self.time_elapsed = 0.0
        self.bullet_spawn_timer = 0.0
        self.trap_spawn_timer = 0.0
        self.bullet_spawn_interval = 3.0
        self.trap_spawn_interval = 8.0
        if self.collision_manager:
            self.collision_manager.reset_caches()
