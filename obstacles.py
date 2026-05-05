"""
Environment obstacles for Grid Survival.
Static and dynamic obstacles that appear on the map - crates, barrels, spikes, etc.
"""

import random
import math
import pygame
from typing import List, Tuple, Optional

from settings import ASSETS_DIR, WINDOW_SIZE


OBSTACLES_DIR = ASSETS_DIR / "Obstacles"


class ObstacleType:
    """Types of obstacles available."""
    CRATE = "crate"
    BARREL = "barrel"
    SPIKES = "spikes"
    BOULDER = "boulder"
    TREE = "tree"
    PILLAR = "pillar"


OBSTACLE_CONFIGS = {
    ObstacleType.CRATE: {
        "width": 48,
        "height": 48,
        "color": (139, 90, 43),
        "destructible": True,
        "health": 2,
    },
    ObstacleType.BARREL: {
        "width": 40,
        "height": 56,
        "color": (80, 60, 40),
        "destructible": True,
        "health": 3,
    },
    ObstacleType.SPIKES: {
        "width": 48,
        "height": 32,
        "color": (100, 100, 100),
        "destructible": False,
        "damage": 1,
    },
    ObstacleType.BOULDER: {
        "width": 64,
        "height": 48,
        "color": (90, 80, 70),
        "destructible": True,
        "health": 4,
    },
    ObstacleType.TREE: {
        "width": 32,
        "height": 96,
        "color": (34, 139, 34),
        "destructible": True,
        "health": 5,
    },
    ObstacleType.PILLAR: {
        "width": 40,
        "height": 80,
        "color": (150, 140, 130),
        "destructible": False,
    },
}


class MapObstacle:
    """A single obstacle on the map."""
    
    def __init__(
        self,
        obstacle_type: str,
        position: Tuple[float, float],
        rotation: float = 0,
    ):
        self.obstacle_type = obstacle_type
        self.position = pygame.Vector2(position)
        self.rotation = rotation
        self.active = True
        
        config = OBSTACLE_CONFIGS.get(obstacle_type, OBSTACLE_CONFIGS[ObstacleType.CRATE])
        self.width = config["width"]
        self.height = config["height"]
        self.color = config["color"]
        self.destructible = config.get("destructible", False)
        self.health = config.get("health", 1) if self.destructible else 0
        self.damage = config.get("damage", 0)
        
        self._create_surface()
    
    def _create_surface(self):
        """Create the obstacle surface - try loading asset first, then procedural."""
        loaded = False
        
        asset_map = {
            ObstacleType.CRATE: "crate.png",
        }
        
        asset_name = asset_map.get(self.obstacle_type)
        if asset_name:
            asset_path = OBSTACLES_DIR / asset_name
            if asset_path.exists():
                try:
                    img = pygame.image.load(asset_path.as_posix()).convert_alpha()
                    img_w, img_h = img.get_size()
                    scale = min(self.width / img_w, self.height / img_h) if img_w > 0 and img_h > 0 else 1.0
                    new_size = (int(img_w * scale), int(img_h * scale))
                    img = pygame.transform.smoothscale(img, new_size)
                    self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
                    self.surface.blit(img, (0, 0))
                    loaded = True
                except Exception as e:
                    print(f"Failed to load obstacle asset: {e}")
        
        if not loaded:
            self.surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            
            if self.obstacle_type == ObstacleType.CRATE:
                self._draw_crate()
            elif self.obstacle_type == ObstacleType.BARREL:
                self._draw_barrel()
            elif self.obstacle_type == ObstacleType.SPIKES:
                self._draw_spikes()
            elif self.obstacle_type == ObstacleType.BOULDER:
                self._draw_boulder()
            elif self.obstacle_type == ObstacleType.TREE:
                self._draw_tree()
            elif self.obstacle_type == ObstacleType.PILLAR:
                self._draw_pillar()
            else:
                pygame.draw.rect(self.surface, self.color, (0, 0, self.width, self.height))
    
    def _draw_crate(self):
        """Draw a wooden crate."""
        base_color = self.color
        dark_color = (base_color[0] - 30, base_color[1] - 20, base_color[2] - 10)
        light_color = (min(255, base_color[0] + 20), min(255, base_color[1] + 15), min(255, base_color[2] + 10))
        
        pygame.draw.rect(self.surface, base_color, (4, 4, self.width - 8, self.height - 8), border_radius=3)
        
        pygame.draw.line(self.surface, dark_color, (4, self.height // 2), (self.width - 4, self.height // 2), 2)
        pygame.draw.line(self.surface, dark_color, (self.width // 2, 4), (self.width // 2, self.height - 4), 2)
        
        pygame.draw.rect(self.surface, dark_color, (4, 4, self.width - 8, self.height - 8), 2, border_radius=3)
        
        for x in [12, self.width - 16]:
            for y in [12, self.height - 16]:
                pygame.draw.circle(self.surface, light_color, (x, y), 3)
    
    def _draw_barrel(self):
        """Draw a barrel."""
        mid_y = self.height // 2
        
        pygame.draw.ellipse(self.surface, self.color, (4, 4, self.width - 8, 20))
        
        pygame.draw.rect(self.surface, self.color, (4, 14, self.width - 8, self.height - 28))
        
        pygame.draw.ellipse(self.surface, self.color, (4, self.height - 20, self.width - 8, 18))
        
        band_color = (60, 50, 40)
        pygame.draw.ellipse(self.surface, band_color, (4, 8, self.width - 8, 10))
        pygame.draw.ellipse(self.surface, band_color, (4, self.height - 16, self.width - 8, 10))
        
        dark_color = (self.color[0] - 20, self.color[1] - 15, self.color[2] - 10)
        pygame.draw.ellipse(self.surface, dark_color, (4, 4, self.width - 8, 20), 2)
        pygame.draw.ellipse(self.surface, dark_color, (4, self.height - 20, self.width - 8, 18), 2)
    
    def _draw_spikes(self):
        """Draw metal spikes."""
        metal_color = self.color
        dark_metal = (metal_color[0] - 30, metal_color[1] - 30, metal_color[2] - 30)
        
        base_rect = pygame.Rect(4, self.height - 12, self.width - 8, 10)
        pygame.draw.rect(self.surface, dark_metal, base_rect, border_radius=2)
        
        spike_count = 5
        spike_width = (self.width - 16) // spike_count
        for i in range(spike_count):
            x = 8 + i * spike_width
            points = [
                (x, self.height - 14),
                (x + spike_width // 2, 4),
                (x + spike_width, self.height - 14),
            ]
            pygame.draw.polygon(self.surface, metal_color, points)
            pygame.draw.polygon(self.surface, dark_metal, points, 1)
    
    def _draw_boulder(self):
        """Draw a boulder/rock."""
        points = [
            (self.width * 0.15, self.height * 0.7),
            (self.width * 0.1, self.height * 0.4),
            (self.width * 0.25, self.height * 0.15),
            (self.width * 0.5, self.height * 0.05),
            (self.width * 0.75, self.height * 0.2),
            (self.width * 0.9, self.height * 0.45),
            (self.width * 0.85, self.height * 0.75),
            (self.width * 0.6, self.height * 0.9),
            (self.width * 0.35, self.height * 0.85),
        ]
        pygame.draw.polygon(self.surface, self.color, points)
        
        dark_color = (self.color[0] - 25, self.color[1] - 20, self.color[2] - 15)
        pygame.draw.polygon(self.surface, dark_color, points, 2)
        
        highlight = (min(255, self.color[0] + 30), min(255, self.color[1] + 25), min(255, self.color[2] + 20))
        pygame.draw.circle(self.surface, highlight, (int(self.width * 0.4), int(self.height * 0.35)), 8)
    
    def _draw_tree(self):
        """Draw a stylized tree."""
        trunk_width = 12
        trunk_height = self.height * 0.4
        
        trunk_rect = pygame.Rect(
            (self.width - trunk_width) // 2,
            self.height - trunk_height,
            trunk_width,
            trunk_height
        )
        pygame.draw.rect(self.surface, (101, 67, 33), trunk_rect)
        
        pygame.draw.rect(self.surface, (80, 50, 25), trunk_rect, 2)
        
        foliage_color = self.color
        for i in range(3):
            radius = self.width // 2 - 4 - i * 4
            center_y = self.height - trunk_height - 10 - i * 12
            pygame.draw.circle(self.surface, foliage_color, (self.width // 2, center_y), radius)
        
        dark_foliage = (foliage_color[0] - 20, foliage_color[1] - 40, foliage_color[2] - 20)
        pygame.draw.circle(self.surface, dark_foliage, (self.width // 2 + 4, self.height - trunk_height - 15), 10)
    
    def _draw_pillar(self):
        """Draw a stone pillar."""
        pygame.draw.rect(self.surface, self.color, (4, 8, self.width - 8, self.height - 12), border_radius=2)
        
        dark_color = (self.color[0] - 30, self.color[1] - 25, self.color[2] - 20)
        pygame.draw.rect(self.surface, dark_color, (4, 4, self.width - 8, 10), border_radius=2)
        pygame.draw.rect(self.surface, dark_color, (4, self.height - 12, self.width - 8, 8), border_radius=2)
        
        pygame.draw.rect(self.surface, dark_color, (4, 8, self.width - 8, self.height - 12), 2, border_radius=2)
    
    def take_damage(self, amount: int = 1) -> bool:
        """Apply damage to obstacle. Returns True if destroyed."""
        if not self.destructible:
            return False
        
        self.health -= amount
        if self.health <= 0:
            self.active = False
            return True
        return False
    
    def get_rect(self) -> pygame.Rect:
        """Get the collision rect for this obstacle."""
        return pygame.Rect(
            int(self.position.x - self.width // 2),
            int(self.position.y - self.height // 2),
            self.width,
            self.height,
        )
    
    def draw(self, surface: pygame.Surface):
        """Draw the obstacle."""
        if not self.active:
            return
        
        rect = self.surface.get_rect(center=(int(self.position.x), int(self.position.y)))
        
        if self.rotation != 0:
            rotated = pygame.transform.rotate(self.surface, self.rotation)
            rotated_rect = rotated.get_rect(center=rect.center)
            surface.blit(rotated, rotated_rect)
        else:
            surface.blit(self.surface, rect)
    
    def check_collision(self, player) -> bool:
        """Check if obstacle hits player."""
        if not self.active:
            return False
        
        if self.damage > 0:
            hitbox = player.get_hitbox() if hasattr(player, 'get_hitbox') else player.rect
            return self.get_rect().colliderect(hitbox)
        return False
    
    def snapshot_state(self) -> dict:
        """Serialize obstacle state for network sync."""
        return {
            "type": self.obstacle_type,
            "x": float(self.position.x),
            "y": float(self.position.y),
            "rotation": float(self.rotation),
            "active": self.active,
            "health": self.health if self.destructible else 0,
        }
    
    @classmethod
    def from_snapshot(cls, snapshot: dict) -> "MapObstacle":
        """Create obstacle from snapshot."""
        obstacle = cls(
            snapshot.get("type", ObstacleType.CRATE),
            (snapshot.get("x", 0), snapshot.get("y", 0)),
            snapshot.get("rotation", 0),
        )
        obstacle.active = snapshot.get("active", True)
        if obstacle.destructible:
            obstacle.health = snapshot.get("health", obstacle.health)
        return obstacle


class ObstacleManager:
    """Manages all obstacles on the map."""
    
    def __init__(self):
        self.obstacles: List[MapObstacle] = []
        self.spawn_timer = 0.0
        self.spawn_interval = 15.0
        self.max_obstacles = 8
    
    def update(self, dt: float, game_time: float):
        """Update obstacles."""
        if game_time < 20.0:
            return
        
        for obstacle in self.obstacles:
            if not obstacle.active:
                continue
        
        self.spawn_timer += dt
        if self.spawn_timer >= self.spawn_interval and len(self.obstacles) < self.max_obstacles:
            self.spawn_timer = 0
            self._spawn_obstacle()
    
    def _spawn_obstacle(self):
        """Spawn a random obstacle."""
        obstacle_types = list(OBSTACLE_CONFIGS.keys())
        obstacle_type = random.choice(obstacle_types)
        
        margin = 120
        x = random.randint(margin, WINDOW_SIZE[0] - margin)
        y = random.randint(margin, WINDOW_SIZE[1] - margin)
        
        rotation = random.choice([0, 90, 180, 270])
        
        self.obstacles.append(MapObstacle(obstacle_type, (x, y), rotation))
    
    def check_player_collision(self, player) -> bool:
        """Check if player hits a damaging obstacle."""
        for obstacle in self.obstacles:
            if obstacle.check_collision(player):
                return True
        return False
    
    def destroy_nearby(self, position: pygame.Vector2, radius: float) -> List[MapObstacle]:
        """Destroy destructible obstacles near a position."""
        destroyed = []
        for obstacle in self.obstacles:
            if not obstacle.destructible or not obstacle.active:
                continue
            if obstacle.position.distance_to(position) < radius:
                if obstacle.take_damage():
                    destroyed.append(obstacle)
        return destroyed
    
    def draw(self, surface: pygame.Surface):
        """Draw all obstacles."""
        for obstacle in self.obstacles:
            obstacle.draw(surface)
    
    def reset(self):
        """Reset all obstacles."""
        self.obstacles.clear()
        self.spawn_timer = 0.0
    
    def snapshot_state(self) -> dict:
        """Serialize all obstacles for network sync."""
        return {
            "obstacles": [o.snapshot_state() for o in self.obstacles],
            "spawn_timer": float(self.spawn_timer),
        }
    
    def apply_snapshot(self, snapshot: dict | None):
        """Apply obstacle snapshot from network."""
        if not isinstance(snapshot, dict):
            return
        
        self.spawn_timer = float(snapshot.get("spawn_timer", 0.0))
        
        self.obstacles = []
        for obs_state in snapshot.get("obstacles", []) or []:
            if isinstance(obs_state, dict):
                self.obstacles.append(MapObstacle.from_snapshot(obs_state))