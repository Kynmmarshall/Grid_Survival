"""
TMX-based tile disappearance system for Grid Survival.
Manages tile states (Normal, Warning, Disappeared) directly on isometric TMX tiles.
"""

import random
import pygame
from enum import Enum
from typing import List, Dict, Tuple, Optional

from settings import WINDOW_SIZE, WALKABLE_LAYER_NAMES


class TileState(Enum):
    """Tile lifecycle states."""
    NORMAL = "normal"
    WARNING = "warning"
    DISAPPEARED = "disappeared"


class TMXTile:
    """Individual TMX tile with state management and visual effects."""
    
    def __init__(self, grid_x: int, grid_y: int, pixel_x: int, pixel_y: int, 
                 tile_width: int, tile_height: int, gid: int):
        self.grid_x = grid_x  # TMX grid column
        self.grid_y = grid_y  # TMX grid row
        self.pixel_x = pixel_x  # Isometric screen X position
        self.pixel_y = pixel_y  # Isometric screen Y position
        self.tile_width = tile_width
        self.tile_height = tile_height
        self.gid = gid  # Global tile ID from TMX
        
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
    
    def get_diamond_points(self) -> List[Tuple[int, int]]:
        """Get the diamond-shaped overlay points for isometric tile."""
        # Calculate diamond points for isometric tile top face
        half_width = self.tile_width / 2
        half_height = self.tile_height / 2
        
        center_x = self.pixel_x + half_width
        top_y = self.pixel_y
        
        points = [
            (int(center_x), int(top_y)),  # Top
            (int(center_x + half_width), int(top_y + half_height)),  # Right
            (int(center_x), int(top_y + self.tile_height)),  # Bottom
            (int(center_x - half_width), int(top_y + half_height)),  # Left
        ]
        return points


class TMXTileManager:
    """
    Manages tile disappearance directly on TMX isometric tiles.
    Works with the existing TMX map data and walkable mask.
    """
    
    def __init__(self, tmx_data, scale_x: float = 1.0, scale_y: float = 1.0):
        self.tmx_data = tmx_data
        self.scale_x = scale_x
        self.scale_y = scale_y
        self.tiles: Dict[Tuple[int, int], TMXTile] = {}
        self.disappeared_tiles: List[TMXTile] = []
        
        # Difficulty scaling parameters
        self.time_elapsed = 0.0
        self.base_disappear_interval = 3.0  # seconds between disappearances
        self.min_disappear_interval = 0.8  # minimum interval at high difficulty
        self.difficulty_scale_rate = 0.95  # multiplier per disappearance
        self.current_interval = self.base_disappear_interval
        self.disappear_timer = 0.0
        self.simultaneous_tiles = 1  # how many tiles disappear at once
        
        # Build tile registry from TMX data
        self._build_tile_registry()
    
    def _build_tile_registry(self):
        """Build registry of walkable tiles from TMX data."""
        if not self.tmx_data:
            return
        
        # Find walkable layers
        target_layers = {name.lower() for name in WALKABLE_LAYER_NAMES}
        
        for layer in self.tmx_data.layers:
            if getattr(layer, "name", "").lower() not in target_layers:
                continue
            if not hasattr(layer, "tiles"):
                continue
            
            # Iterate through all tiles in the layer
            for x, y, gid in layer:
                if gid == 0:  # Empty tile
                    continue
                
                # Calculate isometric pixel position
                pixel_x, pixel_y = self._tile_to_pixel(x, y, layer)
                
                # Scale to window size
                scaled_x = int(pixel_x * self.scale_x)
                scaled_y = int(pixel_y * self.scale_y)
                scaled_width = int(self.tmx_data.tilewidth * self.scale_x)
                scaled_height = int(self.tmx_data.tileheight * self.scale_y)
                
                # Create tile entry
                tile = TMXTile(x, y, scaled_x, scaled_y, scaled_width, scaled_height, gid)
                self.tiles[(x, y)] = tile
    
    def _tile_to_pixel(self, x: int, y: int, layer) -> Tuple[int, int]:
        """Convert TMX grid coordinates to isometric pixel coordinates."""
        layer_offset_x = getattr(layer, "offsetx", 0)
        layer_offset_y = getattr(layer, "offsety", 0)
        
        if self.tmx_data.orientation == "isometric":
            half_width = self.tmx_data.tilewidth / 2
            half_height = self.tmx_data.tileheight / 2
            origin_x = self.tmx_data.height * half_width
            pixel_x = (x - y) * half_width + origin_x
            pixel_y = (x + y) * half_height
        else:
            pixel_x = x * self.tmx_data.tilewidth
            pixel_y = y * self.tmx_data.tileheight
        
        pixel_x += layer_offset_x
        pixel_y += layer_offset_y
        return int(round(pixel_x)), int(round(pixel_y))
    
    def update(self, dt: float):
        """Update all tiles and handle disappearance logic."""
        self.time_elapsed += dt
        self.disappear_timer += dt
        
        # Update existing tiles
        for tile in self.tiles.values():
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
        normal_tiles = [t for t in self.tiles.values() if t.state == TileState.NORMAL]
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
    
    def draw_warning_overlays(self, surface: pygame.Surface):
        """Draw warning overlays on tiles that are in WARNING state."""
        for tile in self.tiles.values():
            if tile.state == TileState.WARNING:
                # Create semi-transparent warning overlay
                points = tile.get_diamond_points()
                
                # Draw pulsing orange/red diamond overlay
                color = (255, 150, 0, tile.alpha)  # Orange with pulsing alpha
                
                # Create temporary surface for alpha blending
                temp_surface = pygame.Surface((tile.tile_width, tile.tile_height), pygame.SRCALPHA)
                
                # Adjust points relative to temp surface
                adjusted_points = [
                    (p[0] - tile.pixel_x, p[1] - tile.pixel_y) for p in points
                ]
                
                pygame.draw.polygon(temp_surface, color, adjusted_points)
                pygame.draw.polygon(temp_surface, (255, 100, 0), adjusted_points, 3)  # Border
                
                surface.blit(temp_surface, (tile.pixel_x, tile.pixel_y))
    
    def get_updated_walkable_mask(self, original_mask: pygame.mask.Mask) -> pygame.mask.Mask:
        """
        Generate updated walkable mask with disappeared tiles removed.
        Returns a copy of the original mask with disappeared tiles erased.
        """
        if not original_mask:
            return None
        
        # Create a copy of the original mask
        updated_mask = original_mask.copy()
        
        # Erase disappeared tiles from the mask
        for tile in self.tiles.values():
            if tile.state == TileState.DISAPPEARED:
                # Create a mask for this tile's diamond shape
                tile_surface = pygame.Surface((tile.tile_width, tile.tile_height), pygame.SRCALPHA)
                points = [
                    (p[0] - tile.pixel_x, p[1] - tile.pixel_y) 
                    for p in tile.get_diamond_points()
                ]
                pygame.draw.polygon(tile_surface, (255, 255, 255, 255), points)
                tile_mask = pygame.mask.from_surface(tile_surface)
                
                # Erase this tile from the walkable mask
                updated_mask.erase(tile_mask, (tile.pixel_x, tile.pixel_y))
        
        return updated_mask
    
    def should_render_tile(self, grid_x: int, grid_y: int) -> bool:
        """Check if a tile at grid position should be rendered."""
        tile = self.tiles.get((grid_x, grid_y))
        if not tile:
            return True  # Not in our registry, render normally
        return tile.state != TileState.DISAPPEARED
    
    def reset(self):
        """Reset all tiles to normal state."""
        for tile in self.tiles.values():
            tile.reset()
        self.disappeared_tiles.clear()
        self.time_elapsed = 0.0
        self.current_interval = self.base_disappear_interval
        self.disappear_timer = 0.0
        self.simultaneous_tiles = 1
