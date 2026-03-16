"""
Tile disappearance system for Grid Survival.
Manages tile states (Normal, Warning, Disappeared) and random tile removal logic.
"""

import random
import pygame
from enum import Enum
from typing import List, Tuple, Optional

from settings import WINDOW_SIZE


class TileState(Enum):
    """Tile lifecycle states."""
    NORMAL = "normal"
    WARNING = "warning"
    DISAPPEARED = "disappeared"


class Tile:
    """Individual tile with state management and visual effects."""
    
    def __init__(self, rect: pygame.Rect, tile_id: int):
        self.rect = rect
        self.tile_id = tile_id
        self.state = TileState.NORMAL
        self.warning_timer = 0.0
        self.warning_duration = 1.5  # seconds before disappearing
        self.flash_speed = 8.0  # flashes per second
        self.alpha = 255
        
    def update(self, dt: float) -> bool:
        """Update tile state. Returns True if tile just disappeared."""
        if self.state == TileState.WARNING:
            self.warning_timer += dt
            # Flash effect during warning
            flash_cycle = (self.warning_timer * self.flash_speed) % 1.0
            self.alpha = int(100 + 155 * flash_cycle)
            
            if self.warning_timer >= self.warning_duration:
                self.state = TileState.DISAPPEARED
                self.alpha = 0
                return True
        return False
    
    def set_warning(self):
        """Trigger warning state."""
        if self.state == TileState.NORMAL:
            self.state = TileState.WARNING
            self.warning_timer = 0.0
    
    def is_walkable(self) -> bool:
        """Check if tile can be walked on."""
        return self.state == TileState.NORMAL
    
    def is_disappeared(self) -> bool:
        """Check if tile has disappeared."""
        return self.state == TileState.DISAPPEARED
    
    def reset(self):
        """Reset tile to normal state."""
        self.state = TileState.NORMAL
        self.warning_timer = 0.0
        self.alpha = 255


class TileGrid:
    """
    Manages a grid of tiles with disappearance logic.
    Works alongside the TMX walkable mask system.
    """
    
    def __init__(self, grid_width: int = 10, grid_height: int = 6, tile_size: int = 64):
        self.grid_width = grid_width
        self.grid_height = grid_height
        self.tile_size = tile_size
        self.tiles: List[Tile] = []
        self.disappeared_tiles: List[Tile] = []
        
        # Difficulty scaling parameters
        self.time_elapsed = 0.0
        self.base_disappear_interval = 3.0  # seconds between disappearances
        self.min_disappear_interval = 0.8  # minimum interval at high difficulty
        self.difficulty_scale_rate = 0.95  # multiplier per disappearance
        self.current_interval = self.base_disappear_interval
        self.disappear_timer = 0.0
        self.simultaneous_tiles = 1  # how many tiles disappear at once
        
        # Center the grid on screen
        total_width = grid_width * tile_size
        total_height = grid_height * tile_size
        start_x = (WINDOW_SIZE[0] - total_width) // 2
        start_y = (WINDOW_SIZE[1] - total_height) // 2
        
        # Create tile grid
        tile_id = 0
        for row in range(grid_height):
            for col in range(grid_width):
                x = start_x + col * tile_size
                y = start_y + row * tile_size
                rect = pygame.Rect(x, y, tile_size, tile_size)
                self.tiles.append(Tile(rect, tile_id))
                tile_id += 1
    
    def update(self, dt: float):
        """Update all tiles and handle disappearance logic."""
        self.time_elapsed += dt
        self.disappear_timer += dt
        
        # Update existing tiles
        for tile in self.tiles:
            if tile.update(dt):
                self.disappeared_tiles.append(tile)
        
        # Trigger new tile warnings based on difficulty
        if self.disappear_timer >= self.current_interval:
            self.disappear_timer = 0.0
            self._trigger_random_tiles()
            
            # Increase difficulty
            self.current_interval = max(
                self.min_disappear_interval,
                self.current_interval * self.difficulty_scale_rate
            )
            
            # Increase simultaneous tiles every 30 seconds
            if self.time_elapsed > 30 and self.simultaneous_tiles < 3:
                self.simultaneous_tiles = 2
            elif self.time_elapsed > 60 and self.simultaneous_tiles < 4:
                self.simultaneous_tiles = 3
    
    def _trigger_random_tiles(self):
        """Select random normal tiles and set them to warning state."""
        normal_tiles = [t for t in self.tiles if t.state == TileState.NORMAL]
        if not normal_tiles:
            return
        
        # Don't remove all tiles - keep at least 30% available
        min_safe_tiles = max(3, int(len(self.tiles) * 0.3))
        if len(normal_tiles) <= min_safe_tiles:
            return
        
        # Select tiles to warn
        num_to_warn = min(self.simultaneous_tiles, len(normal_tiles) - min_safe_tiles)
        tiles_to_warn = random.sample(normal_tiles, num_to_warn)
        
        for tile in tiles_to_warn:
            tile.set_warning()
    
    def draw(self, surface: pygame.Surface):
        """Draw all tiles with their current states."""
        for tile in self.tiles:
            if tile.state == TileState.DISAPPEARED:
                continue
            
            # Draw tile based on state
            if tile.state == TileState.NORMAL:
                color = (100, 150, 200)  # Blue
                pygame.draw.rect(surface, color, tile.rect)
                pygame.draw.rect(surface, (80, 120, 160), tile.rect, 2)
            elif tile.state == TileState.WARNING:
                # Warning flash effect
                color = (255, 200, 0, tile.alpha)  # Yellow/Orange
                tile_surface = pygame.Surface(tile.rect.size, pygame.SRCALPHA)
                pygame.draw.rect(tile_surface, color, tile_surface.get_rect())
                pygame.draw.rect(tile_surface, (255, 100, 0), tile_surface.get_rect(), 3)
                surface.blit(tile_surface, tile.rect.topleft)
    
    def get_walkable_mask(self) -> pygame.mask.Mask:
        """
        Generate a mask representing currently walkable tiles.
        This can be combined with the TMX walkable mask.
        """
        mask_surface = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        
        for tile in self.tiles:
            if tile.is_walkable():
                pygame.draw.rect(mask_surface, (255, 255, 255, 255), tile.rect)
        
        return pygame.mask.from_surface(mask_surface)
    
    def is_position_safe(self, position: pygame.Vector2) -> bool:
        """Check if a position is over a walkable tile."""
        for tile in self.tiles:
            if tile.is_walkable() and tile.rect.collidepoint(position.x, position.y):
                return True
        return False
    
    def get_tile_at_position(self, position: pygame.Vector2) -> Optional[Tile]:
        """Get the tile at a specific position."""
        for tile in self.tiles:
            if tile.rect.collidepoint(position.x, position.y):
                return tile
        return None
    
    def reset(self):
        """Reset all tiles to normal state."""
        for tile in self.tiles:
            tile.reset()
        self.disappeared_tiles.clear()
        self.time_elapsed = 0.0
        self.current_interval = self.base_disappear_interval
        self.disappear_timer = 0.0
        self.simultaneous_tiles = 1
    
    def get_safe_spawn_position(self) -> Optional[pygame.Vector2]:
        """Get a random safe position for spawning."""
        normal_tiles = [t for t in self.tiles if t.state == TileState.NORMAL]
        if not normal_tiles:
            return None
        
        tile = random.choice(normal_tiles)
        return pygame.Vector2(tile.rect.centerx, tile.rect.centery)
