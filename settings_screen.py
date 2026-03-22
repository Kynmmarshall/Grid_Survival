"""
GRID SURVIVAL - Fully Responsive Settings Screen
Everything scales perfectly for ANY screen size
"""

import pygame
import sys
import json
import math
import random
import os
from pygame.locals import *

# Initialize Pygame
pygame.init()
pygame.mixer.init()

# ==================== BASE DESIGN RESOLUTION ====================
# All UI elements are designed at 1280x720 and scale to any screen
BASE_WIDTH = 1280
BASE_HEIGHT = 720
FPS = 60

# ==================== COLOR SCHEME ====================
PRIMARY_BLUE = (0, 180, 255)
DEEP_BLUE = (0, 100, 200)
PRIMARY_RED = (255, 50, 50)
BLOOD_RED = (200, 30, 30)
GOLD = (255, 215, 0)
SILVER = (192, 192, 192)
WHITE = (255, 255, 255)
LIGHT_GRAY = (200, 200, 200)
DARK_GRAY = (40, 40, 50)
BLACK = (0, 0, 0)
BG_DARK = (8, 12, 20)
BG_MID = (15, 20, 30)
SUCCESS_GREEN = (0, 255, 100)

# Available Resolutions
AVAILABLE_RESOLUTIONS = [
    (1024, 768),
    (1280, 720),
    (1366, 768),
    (1600, 900),
    (1920, 1080),
    (2560, 1440),
    (3840, 2160),
]

# Graphics Quality Presets
GRAPHICS_PRESETS = {
    "Low": {"shadow_quality": "Low", "texture_quality": "Low", "antialiasing": False,
            "post_processing": False, "draw_distance": 50, "reflection_quality": "Low"},
    "Medium": {"shadow_quality": "Medium", "texture_quality": "Medium", "antialiasing": True,
               "post_processing": False, "draw_distance": 75, "reflection_quality": "Medium"},
    "High": {"shadow_quality": "High", "texture_quality": "High", "antialiasing": True,
             "post_processing": True, "draw_distance": 100, "reflection_quality": "High"},
    "Ultra": {"shadow_quality": "Ultra", "texture_quality": "Ultra", "antialiasing": True,
              "post_processing": True, "draw_distance": 120, "reflection_quality": "Ultra"}
}

# ==================== RESPONSIVE SCALING SYSTEM ====================

class ResponsiveScale:
    """Handles all scaling calculations for responsive UI"""
    def __init__(self, screen_width, screen_height):
        self.update(screen_width, screen_height)
        
    def update(self, screen_width, screen_height):
        self.screen_width = screen_width
        self.screen_height = screen_height
        # Calculate scale factors based on base resolution
        self.scale_x = screen_width / BASE_WIDTH
        self.scale_y = screen_height / BASE_HEIGHT
        self.scale = min(self.scale_x, self.scale_y)  # Uniform scale for size
        # Aspect ratio adjustments
        self.aspect_ratio = screen_width / screen_height
        self.base_aspect = BASE_WIDTH / BASE_HEIGHT
        
    def x(self, value):
        """Scale horizontal position/size"""
        return int(value * self.scale_x)
    
    def y(self, value):
        """Scale vertical position/size"""
        return int(value * self.scale_y)
    
    def s(self, value):
        """Scale size uniformly (maintains proportions)"""
        return int(value * self.scale)
    
    def rect(self, x, y, w, h):
        """Create a scaled rectangle"""
        return pygame.Rect(self.x(x), self.y(y), self.x(w), self.y(h))
    
    def font_size(self, base_size):
        """Scale font size"""
        return max(8, int(base_size * self.scale))

# ==================== PARTICLE SYSTEM ====================

class Particle:
    def __init__(self, x, y, vx, vy, color, size, lifetime):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.size = size
        self.lifetime = lifetime
        self.max_lifetime = lifetime
        
    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.lifetime -= 1
        return self.lifetime > 0
        
    def draw(self, surface, scale):
        x_scaled = int(self.x * scale.scale_x)
        y_scaled = int(self.y * scale.scale_y)
        size_scaled = scale.s(self.size)
        if size_scaled > 0:
            pygame.draw.circle(surface, self.color, (x_scaled, y_scaled), max(1, size_scaled))

class ParticleSystem:
    def __init__(self):
        self.particles = []
        
    def add_burst(self, x, y, count, color, speed_range=(1, 5), size_range=(1, 3)):
        for _ in range(count):
            angle = random.uniform(0, math.pi * 2)
            speed = random.uniform(*speed_range)
            vx = math.cos(angle) * speed
            vy = math.sin(angle) * speed
            size = random.uniform(*size_range)
            lifetime = random.randint(30, 60)
            self.particles.append(Particle(x, y, vx, vy, color, size, lifetime))
            
    def add_floaters(self, count, rect, scale, color):
        for _ in range(count):
            x = random.uniform(rect.left, rect.right) / scale.scale_x
            y = random.uniform(rect.top, rect.bottom) / scale.scale_y
            vx = random.uniform(-0.3, 0.3)
            vy = random.uniform(-0.3, 0.3)
            size = random.uniform(0.5, 1.5)
            lifetime = random.randint(120, 240)
            self.particles.append(Particle(x, y, vx, vy, color, size, lifetime))
            
    def add_trail(self, x, y, color):
        self.particles.append(Particle(x, y, random.uniform(-1, 1), random.uniform(-1.5, 0), 
                                       color, 1.5, 20))
        
    def update(self):
        self.particles = [p for p in self.particles if p.update()]
        
    def draw(self, surface, scale):
        for particle in self.particles:
            particle.draw(surface, scale)

# ==================== RESPONSIVE BACKGROUND ====================

class ResponsiveBackground:
    """Background that scales perfectly to any screen size"""
    def __init__(self):
        self.angle = 0
        
    def update(self):
        self.angle += 0.005
        
    def draw(self, surface, scale):
        w = scale.screen_width
        h = scale.screen_height
        
        # Gradient background that scales
        for y in range(h):
            t = y / h
            r = int(BG_DARK[0] * (1 - t) + BG_MID[0] * t)
            g = int(BG_DARK[1] * (1 - t) + BG_MID[1] * t)
            b = int(BG_DARK[2] * (1 - t) + BG_MID[2] * t)
            pygame.draw.line(surface, (r, g, b), (0, y), (w, y))
        
        # Grid effect - scales with screen
        cx = w // 2
        cy = scale.y(240)
        
        for angle in range(0, 360, 45):
            rad = math.radians(angle + self.angle * 50)
            for dist in range(scale.s(100), scale.s(400), scale.s(100)):
                x = cx + math.cos(rad) * dist
                y = cy + math.sin(rad) * dist * 0.5
                if 0 <= x < w:
                    color = PRIMARY_BLUE if angle % 90 == 0 else DEEP_BLUE
                    line_width = max(1, scale.s(1))
                    pygame.draw.line(surface, color, (cx, cy), (int(x), int(y)), line_width)
        
        # Floating orbs - scale with screen
        for i in range(6):
            a = self.angle * 2 + i * math.pi / 3
            x = cx + math.cos(a) * scale.s(180)
            y = cy + math.sin(a * 1.5) * scale.s(60)
            size = scale.s(2 + math.sin(self.angle * 2 + i) * 1)
            pygame.draw.circle(surface, PRIMARY_BLUE, (int(x), int(y)), max(1, int(size)))

# ==================== RESPONSIVE UI WIDGETS ====================

class ResponsiveWidget:
    """Base class for all responsive widgets"""
    def __init__(self):
        self.prioritized = False
        self.priority_timer = 0
        self.hover = False
        
    def set_prioritized(self):
        self.prioritized = True
        self.priority_timer = 30
        
    def update_priority(self):
        if self.priority_timer > 0:
            self.priority_timer -= 1
            if self.priority_timer == 0:
                self.prioritized = False

class ResponsiveButton(ResponsiveWidget):
    def __init__(self, x, y, width, height, text, color):
        super().__init__()
        self.base_x = x
        self.base_y = y
        self.base_w = width
        self.base_h = height
        self.text = text
        self.color = color
        self.click_timer = 0
        self.rect = pygame.Rect(0, 0, 0, 0)
        
    def update_scale(self, scale):
        self.rect = scale.rect(self.base_x, self.base_y, self.base_w, self.base_h)
        self.font_size = scale.font_size(28)
        
    def handle_event(self, event, scale):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and self.hover:
            self.click_timer = 6
            self.set_prioritized()
            return True
        return False
        
    def update(self):
        if self.click_timer > 0:
            self.click_timer -= 1
        self.update_priority()
        
    def draw(self, surface, scale):
        # Determine scale factor based on state
        if self.prioritized:
            scale_factor = 1.12
            border = max(1, scale.s(4))
            glow = True
        elif self.click_timer > 0:
            scale_factor = 0.96
            border = max(1, scale.s(3))
            glow = False
        elif self.hover:
            scale_factor = 1.05
            border = max(1, scale.s(3))
            glow = True
        else:
            scale_factor = 1.0
            border = max(1, scale.s(2))
            glow = False
            
        # Scaled rectangle
        scaled_w = int(self.rect.width * scale_factor)
        scaled_h = int(self.rect.height * scale_factor)
        scaled_rect = pygame.Rect(
            self.rect.centerx - scaled_w // 2,
            self.rect.centery - scaled_h // 2,
            scaled_w, scaled_h
        )
        
        # Glow effect
        if glow:
            for i in range(3):
                glow_rect = scaled_rect.inflate(scale.s(15 + i*5), scale.s(15 + i*5))
                alpha = 80 - i * 25
                surf = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(surf, (*self.color, alpha), surf.get_rect(), border + i)
                surface.blit(surf, glow_rect)
        
        # Button background
        color = self.color
        if self.prioritized:
            color = (min(255, color[0] + 50), min(255, color[1] + 50), min(255, color[2] + 50))
        elif self.hover:
            color = (min(255, color[0] + 30), min(255, color[1] + 30), min(255, color[2] + 30))
            
        pygame.draw.rect(surface, color, scaled_rect)
        border_color = GOLD if self.prioritized else WHITE
        pygame.draw.rect(surface, border_color, scaled_rect, border)
        
        # Text
        font = pygame.font.Font(None, int(self.font_size * (1.05 if self.prioritized else 1.0)))
        text_surf = font.render(self.text, True, WHITE)
        text_rect = text_surf.get_rect(center=scaled_rect.center)
        surface.blit(text_surf, text_rect)

class ResponsiveDropdown(ResponsiveWidget):
    def __init__(self, x, y, width, options, initial_index, color):
        super().__init__()
        self.base_x = x
        self.base_y = y
        self.base_w = width
        self.options = options
        self.selected_index = initial_index
        self.color = color
        self.expanded = False
        self.rect = pygame.Rect(0, 0, 0, 0)
        
    def update_scale(self, scale):
        self.rect = scale.rect(self.base_x, self.base_y, self.base_w, 38)
        self.font_size = scale.font_size(22)
        
    def handle_event(self, event, scale):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
            
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.rect.collidepoint(event.pos):
                self.expanded = not self.expanded
                self.set_prioritized()
                return True
            elif self.expanded:
                for i in range(len(self.options)):
                    opt_rect = pygame.Rect(self.rect.x, self.rect.y + self.rect.height + i * self.rect.height,
                                          self.rect.width, self.rect.height)
                    if opt_rect.collidepoint(event.pos):
                        self.selected_index = i
                        self.expanded = False
                        self.set_prioritized()
                        return True
                self.expanded = False
        return False
        
    def update(self):
        self.update_priority()
        
    def draw(self, surface, scale):
        font = pygame.font.Font(None, self.font_size)
        
        # Glow for prioritized
        if self.prioritized:
            glow_rect = self.rect.inflate(scale.s(15), scale.s(15))
            for i in range(3):
                alpha = 100 - i * 30
                surf = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(surf, (*self.color, alpha), surf.get_rect(), scale.s(3))
                surface.blit(surf, glow_rect)
        
        # Main box
        bg = (80, 80, 100) if self.prioritized else DARK_GRAY
        pygame.draw.rect(surface, bg, self.rect)
        border = GOLD if self.prioritized else (self.color if self.hover else SILVER)
        pygame.draw.rect(surface, border, self.rect, max(1, scale.s(2)))
        
        # Text
        text = font.render(str(self.options[self.selected_index]), True, WHITE)
        surface.blit(text, (self.rect.x + scale.s(10), self.rect.y + scale.s(9)))
        
        # Arrow
        arrow = "▼" if not self.expanded else "▲"
        arrow_surf = font.render(arrow, True, self.color)
        surface.blit(arrow_surf, (self.rect.right - scale.s(25), self.rect.y + scale.s(9)))
        
        # Expanded options
        if self.expanded:
            for i, opt in enumerate(self.options):
                opt_rect = pygame.Rect(self.rect.x, self.rect.y + self.rect.height + i * self.rect.height,
                                      self.rect.width, self.rect.height)
                bg = (80, 80, 100) if i == self.selected_index else DARK_GRAY
                pygame.draw.rect(surface, bg, opt_rect)
                pygame.draw.rect(surface, self.color if i == self.selected_index else DARK_GRAY, opt_rect, 1)
                opt_text = font.render(str(opt), True, WHITE)
                surface.blit(opt_text, (opt_rect.x + scale.s(10), opt_rect.y + scale.s(9)))

class ResponsiveSlider(ResponsiveWidget):
    def __init__(self, x, y, width, min_val, max_val, initial_val, label, color):
        super().__init__()
        self.base_x = x
        self.base_y = y
        self.base_w = width
        self.min_val = min_val
        self.max_val = max_val
        self.value = initial_val
        self.label = label
        self.color = color
        self.dragging = False
        self.rect = pygame.Rect(0, 0, 0, 0)
        
    def update_scale(self, scale):
        self.x = scale.x(self.base_x)
        self.y = scale.y(self.base_y)
        self.width = scale.x(self.base_w)
        self.rect = pygame.Rect(self.x, self.y, self.width, scale.s(6))
        self.font_size = scale.font_size(24)
        
    def handle_event(self, event, scale):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
            
        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            self.dragging = True
            self.set_prioritized()
            self._set_value(event.pos[0])
            return True
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._set_value(event.pos[0])
        return False
        
    def _set_value(self, mouse_x):
        rel = max(0, min(mouse_x - self.rect.x, self.rect.width))
        t = rel / self.rect.width
        self.value = self.min_val + t * (self.max_val - self.min_val)
        
    def update(self):
        self.update_priority()
        
    def draw(self, surface, scale):
        font = pygame.font.Font(None, self.font_size)
        
        # Label
        label_text = f"{self.label}: {int(self.value)}"
        color = GOLD if self.prioritized else (self.color if self.hover else WHITE)
        label_surf = font.render(label_text, True, color)
        surface.blit(label_surf, (self.x, self.y - scale.s(28)))
        
        # Track
        pygame.draw.rect(surface, DARK_GRAY, self.rect)
        
        # Fill
        fill_width = (self.value - self.min_val) / (self.max_val - self.min_val) * self.rect.width
        fill_rect = pygame.Rect(self.x, self.y, fill_width, self.rect.height)
        fill_color = GOLD if self.prioritized else self.color
        pygame.draw.rect(surface, fill_color, fill_rect)
        
        # Handle
        handle_x = self.x + fill_width
        handle_y = self.rect.centery
        handle_radius = scale.s(12 if self.prioritized else 10)
        
        if self.prioritized:
            for i in range(3):
                pygame.draw.circle(surface, (*self.color, 100 - i*30), 
                                 (int(handle_x), int(handle_y)), handle_radius + scale.s(i*3))
        
        pygame.draw.circle(surface, WHITE, (int(handle_x), int(handle_y)), handle_radius)
        pygame.draw.circle(surface, fill_color, (int(handle_x), int(handle_y)), handle_radius - scale.s(2))

class ResponsiveCheckbox(ResponsiveWidget):
    def __init__(self, x, y, label, initial_checked, color):
        super().__init__()
        self.base_x = x
        self.base_y = y
        self.label = label
        self.checked = initial_checked
        self.color = color
        self.rect = pygame.Rect(0, 0, 0, 0)
        
    def update_scale(self, scale):
        self.x = scale.x(self.base_x)
        self.y = scale.y(self.base_y)
        self.size = scale.s(24)
        self.rect = pygame.Rect(self.x, self.y, self.size, self.size)
        self.font_size = scale.font_size(24)
        
    def handle_event(self, event, scale):
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN and self.rect.collidepoint(event.pos):
            self.checked = not self.checked
            self.set_prioritized()
            return True
        return False
        
    def update(self):
        self.update_priority()
        
    def draw(self, surface, scale):
        font = pygame.font.Font(None, self.font_size)
        
        # Glow
        if self.prioritized:
            glow_rect = self.rect.inflate(scale.s(12), scale.s(12))
            for i in range(3):
                alpha = 100 - i * 30
                surf = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(surf, (*self.color, alpha), surf.get_rect(), scale.s(3))
                surface.blit(surf, glow_rect)
        
        # Box
        bg = (80, 80, 100) if self.prioritized else DARK_GRAY
        pygame.draw.rect(surface, bg, self.rect)
        border = GOLD if self.prioritized else (self.color if self.hover else LIGHT_GRAY)
        pygame.draw.rect(surface, border, self.rect, max(1, scale.s(2)))
        
        # Checkmark
        if self.checked:
            center = self.rect.center
            size = scale.s(7)
            points = [(center[0] - size, center[1]), 
                     (center[0] - size//2, center[1] + size),
                     (center[0] + size, center[1] - size)]
            check_color = GOLD if self.prioritized else self.color
            pygame.draw.lines(surface, check_color, False, points, max(1, scale.s(3)))
            
        # Label
        label_color = GOLD if self.prioritized else (self.color if self.hover else LIGHT_GRAY)
        label_surf = font.render(self.label, True, label_color)
        surface.blit(label_surf, (self.rect.right + scale.s(10), self.y))

# ==================== MAIN SETTINGS SCREEN ====================

class SettingsScreen:
    def __init__(self):
        # Start with base resolution
        self.current_res = (BASE_WIDTH, BASE_HEIGHT)
        self.screen = pygame.display.set_mode(self.current_res)
        pygame.display.set_caption("GRID SURVIVAL - Settings")
        self.clock = pygame.time.Clock()
        self.running = True
        
        # Responsive scaling system
        self.scale = ResponsiveScale(self.current_res[0], self.current_res[1])
        
        # Visual systems
        self.background = ResponsiveBackground()
        self.particles = ParticleSystem()
        self.fade = 0
        
        # Settings data
        self.settings = self.load_settings()
        self.create_widgets()
        
        # UI state
        self.feedback = {"text": "", "color": None, "timer": 0}
        self.particles.add_floaters(60, pygame.Rect(0, 0, BASE_WIDTH, BASE_HEIGHT), self.scale, PRIMARY_BLUE)
        
    def load_settings(self):
        default = {
            "resolution": (1920, 1080), "fullscreen": False, "vsync": True,
            "master_volume": 80, "music_volume": 75, "sfx_volume": 70,
            "camera_shake": True, "blood_effects": True,
            "difficulty": "Normal", "graphics_quality": "High",
            "shadow_quality": "High", "texture_quality": "High",
            "antialiasing": True, "post_processing": True,
            "draw_distance": 100, "reflection_quality": "High"
        }
        try:
            if os.path.exists("grid_survival_settings.json"):
                with open("grid_survival_settings.json", 'r') as f:
                    saved = json.load(f)
                    default.update(saved)
        except:
            pass
        return default
        
    def save_settings(self):
        try:
            with open("grid_survival_settings.json", 'w') as f:
                json.dump(self.settings, f, indent=4)
        except:
            pass
            
    def create_widgets(self):
        # LEFT COLUMN - DISPLAY
        res_options = [f"{w}x{h}" for w, h in AVAILABLE_RESOLUTIONS]
        current_res = f"{self.settings['resolution'][0]}x{self.settings['resolution'][1]}"
        res_idx = res_options.index(current_res) if current_res in res_options else 4
        self.res_dropdown = ResponsiveDropdown(80, 160, 200, res_options, res_idx, PRIMARY_BLUE)
        self.fullscreen_check = ResponsiveCheckbox(80, 215, "Fullscreen", self.settings["fullscreen"], PRIMARY_BLUE)
        self.vsync_check = ResponsiveCheckbox(80, 255, "V-Sync", self.settings["vsync"], PRIMARY_BLUE)
        
        # LEFT COLUMN - GAMEPLAY
        self.camera_shake_check = ResponsiveCheckbox(80, 345, "Camera Shake", self.settings["camera_shake"], PRIMARY_RED)
        self.blood_check = ResponsiveCheckbox(80, 385, "Blood Effects", self.settings["blood_effects"], PRIMARY_RED)
        
        # LEFT COLUMN - AUDIO
        self.master_slider = ResponsiveSlider(80, 485, 280, 0, 100, self.settings["master_volume"], "Master Volume", PRIMARY_BLUE)
        self.music_slider = ResponsiveSlider(80, 555, 280, 0, 100, self.settings["music_volume"], "Music Volume", PRIMARY_BLUE)
        self.sfx_slider = ResponsiveSlider(80, 625, 280, 0, 100, self.settings["sfx_volume"], "SFX Volume", PRIMARY_RED)
        
        # RIGHT COLUMN - GRAPHICS
        quality_options = ["Low", "Medium", "High", "Ultra"]
        qual_idx = quality_options.index(self.settings["graphics_quality"])
        self.quality_dropdown = ResponsiveDropdown(720, 160, 180, quality_options, qual_idx, PRIMARY_RED)
        
        shadow_options = ["Low", "Medium", "High", "Ultra"]
        shadow_idx = shadow_options.index(self.settings["shadow_quality"])
        self.shadow_dropdown = ResponsiveDropdown(720, 220, 180, shadow_options, shadow_idx, PRIMARY_BLUE)
        
        texture_options = ["Low", "Medium", "High", "Ultra"]
        texture_idx = texture_options.index(self.settings["texture_quality"])
        self.texture_dropdown = ResponsiveDropdown(720, 280, 180, texture_options, texture_idx, PRIMARY_BLUE)
        
        reflection_options = ["Low", "Medium", "High", "Ultra"]
        reflection_idx = reflection_options.index(self.settings["reflection_quality"])
        self.reflection_dropdown = ResponsiveDropdown(720, 340, 180, reflection_options, reflection_idx, PRIMARY_BLUE)
        
        # RIGHT COLUMN - EFFECTS
        self.antialiasing_check = ResponsiveCheckbox(720, 430, "Anti-Aliasing", self.settings["antialiasing"], PRIMARY_BLUE)
        self.postprocessing_check = ResponsiveCheckbox(720, 470, "Post Processing", self.settings["post_processing"], PRIMARY_BLUE)
        self.draw_distance_slider = ResponsiveSlider(720, 540, 260, 50, 150, self.settings["draw_distance"], "Draw Distance", PRIMARY_BLUE)
        
        # BOTTOM - DIFFICULTY & BUTTONS
        difficulty_options = ["Easy", "Normal", "Hard", "Nightmare"]
        diff_idx = difficulty_options.index(self.settings["difficulty"])
        self.difficulty_dropdown = ResponsiveDropdown(80, 710, 180, difficulty_options, diff_idx, PRIMARY_RED)
        
        # ACTION BUTTONS - Centered
        self.apply_btn = ResponsiveButton(540, 710, 140, 48, "APPLY", SUCCESS_GREEN)
        self.reset_btn = ResponsiveButton(700, 710, 140, 48, "RESET", PRIMARY_RED)
        self.back_btn = ResponsiveButton(860, 710, 140, 48, "BACK", DARK_GRAY)
        
        self.all_widgets = [
            self.res_dropdown, self.fullscreen_check, self.vsync_check,
            self.camera_shake_check, self.blood_check,
            self.master_slider, self.music_slider, self.sfx_slider,
            self.quality_dropdown, self.shadow_dropdown, self.texture_dropdown,
            self.reflection_dropdown, self.antialiasing_check, self.postprocessing_check,
            self.draw_distance_slider, self.difficulty_dropdown,
            self.apply_btn, self.reset_btn, self.back_btn
        ]
        
        self.update_scales()
        
    def update_scales(self):
        for widget in self.all_widgets:
            if hasattr(widget, 'update_scale'):
                widget.update_scale(self.scale)
                
    def apply_quality_preset(self):
        preset = GRAPHICS_PRESETS[self.settings["graphics_quality"]]
        self.settings.update(preset)
        
        shadow_options = ["Low", "Medium", "High", "Ultra"]
        self.shadow_dropdown.selected_index = shadow_options.index(self.settings["shadow_quality"])
        self.texture_dropdown.selected_index = shadow_options.index(self.settings["texture_quality"])
        self.reflection_dropdown.selected_index = shadow_options.index(self.settings["reflection_quality"])
        self.antialiasing_check.checked = self.settings["antialiasing"]
        self.postprocessing_check.checked = self.settings["post_processing"]
        self.draw_distance_slider.value = self.settings["draw_distance"]
        
    def draw_title(self):
        font = pygame.font.Font(None, self.scale.font_size(72))
        title = "GRID SURVIVAL"
        
        # Glow effect
        for i in range(3, 0, -1):
            glow = font.render(title, True, (PRIMARY_RED[0]//i, 0, 0))
            off = self.scale.s(i)
            rect = glow.get_rect(center=(self.scale.screen_width//2 + off, self.scale.y(70) + off))
            self.screen.blit(glow, rect)
            
        # Main title
        main = font.render(title, True, PRIMARY_RED)
        rect = main.get_rect(center=(self.scale.screen_width//2, self.scale.y(70)))
        self.screen.blit(main, rect)
        
        # Subtitle
        font2 = pygame.font.Font(None, self.scale.font_size(24))
        sub = font2.render("SETTINGS", True, PRIMARY_BLUE)
        rect = sub.get_rect(center=(self.scale.screen_width//2, self.scale.y(110)))
        self.screen.blit(sub, rect)
        
    def draw_sections(self):
        font = pygame.font.Font(None, self.scale.font_size(26))
        
        sections = [
            ("DISPLAY", 60, 130, PRIMARY_BLUE),
            ("GAMEPLAY", 60, 315, PRIMARY_RED),
            ("AUDIO", 60, 460, PRIMARY_BLUE),
            ("GRAPHICS", 700, 130, PRIMARY_RED),
            ("EFFECTS", 700, 400, PRIMARY_BLUE),
            ("DIFFICULTY", 60, 685, PRIMARY_RED),
        ]
        
        for text, x, y, color in sections:
            x_scaled = self.scale.x(x)
            y_scaled = self.scale.y(y)
            surf = font.render(text, True, color)
            self.screen.blit(surf, (x_scaled, y_scaled))
            line_y = y_scaled + self.scale.s(25)
            line_width = surf.get_width()
            pygame.draw.line(self.screen, color, (x_scaled, line_y), 
                           (x_scaled + line_width, line_y), max(1, self.scale.s(2)))
        
    def apply_settings(self):
        # Update from widgets
        res_str = self.res_dropdown.options[self.res_dropdown.selected_index]
        w, h = map(int, res_str.split('x'))
        self.settings["resolution"] = (w, h)
        self.settings["fullscreen"] = self.fullscreen_check.checked
        self.settings["vsync"] = self.vsync_check.checked
        self.settings["camera_shake"] = self.camera_shake_check.checked
        self.settings["blood_effects"] = self.blood_check.checked
        self.settings["master_volume"] = int(self.master_slider.value)
        self.settings["music_volume"] = int(self.music_slider.value)
        self.settings["sfx_volume"] = int(self.sfx_slider.value)
        self.settings["graphics_quality"] = self.quality_dropdown.options[self.quality_dropdown.selected_index]
        self.settings["shadow_quality"] = self.shadow_dropdown.options[self.shadow_dropdown.selected_index]
        self.settings["texture_quality"] = self.texture_dropdown.options[self.texture_dropdown.selected_index]
        self.settings["reflection_quality"] = self.reflection_dropdown.options[self.reflection_dropdown.selected_index]
        self.settings["antialiasing"] = self.antialiasing_check.checked
        self.settings["post_processing"] = self.postprocessing_check.checked
        self.settings["draw_distance"] = int(self.draw_distance_slider.value)
        self.settings["difficulty"] = self.difficulty_dropdown.options[self.difficulty_dropdown.selected_index]
        
        self.apply_quality_preset()
        
        # Apply display settings
        flags = pygame.FULLSCREEN if self.settings["fullscreen"] else 0
        try:
            self.current_res = self.settings["resolution"]
            self.screen = pygame.display.set_mode(self.current_res, flags, vsync=self.settings["vsync"])
            self.scale.update(self.screen.get_width(), self.screen.get_height())
            self.update_scales()
        except:
            pass
            
        self.save_settings()
        self.feedback = {"text": "✓ SETTINGS APPLIED", "color": SUCCESS_GREEN, "timer": 60}
        center = self.screen.get_rect().center
        self.particles.add_burst(center[0] / self.scale.scale_x, center[1] / self.scale.scale_y, 
                                80, SUCCESS_GREEN, (2, 8), (2, 5))
        self.apply_btn.set_prioritized()
        
    def reset_settings(self):
        self.settings = {
            "resolution": (1920, 1080), "fullscreen": False, "vsync": True,
            "master_volume": 80, "music_volume": 75, "sfx_volume": 70,
            "camera_shake": True, "blood_effects": True,
            "difficulty": "Normal", "graphics_quality": "High",
            "shadow_quality": "High", "texture_quality": "High",
            "antialiasing": True, "post_processing": True,
            "draw_distance": 100, "reflection_quality": "High"
        }
        self.create_widgets()
        self.feedback = {"text": "⟳ RESET TO DEFAULT", "color": PRIMARY_RED, "timer": 60}
        center = self.screen.get_rect().center
        self.particles.add_burst(center[0] / self.scale.scale_x, center[1] / self.scale.scale_y, 
                                60, PRIMARY_RED, (1, 6), (2, 4))
        self.reset_btn.set_prioritized()
        
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.running = False
                
            for widget in self.all_widgets:
                if hasattr(widget, 'handle_event'):
                    widget.handle_event(event, self.scale)
            
            if self.apply_btn.handle_event(event, self.scale):
                self.apply_settings()
            if self.reset_btn.handle_event(event, self.scale):
                self.reset_settings()
            if self.back_btn.handle_event(event, self.scale):
                self.running = False
                
    def update(self):
        self.particles.update()
        self.background.update()
        
        for widget in self.all_widgets:
            if hasattr(widget, 'update'):
                widget.update()
                
        if self.fade < 255:
            self.fade += 8
            
        if self.feedback["timer"] > 0:
            self.feedback["timer"] -= 1
            
        if random.random() < 0.03:
            x = random.randint(0, self.scale.screen_width) / self.scale.scale_x
            y = random.randint(0, self.scale.screen_height) / self.scale.scale_y
            self.particles.add_trail(x, y, PRIMARY_BLUE)
            
    def draw(self):
        # Draw responsive background
        self.background.draw(self.screen, self.scale)
        
        # Semi-transparent overlay
        overlay = pygame.Surface((self.scale.screen_width, self.scale.screen_height))
        overlay.set_alpha(200)
        overlay.fill(BG_DARK)
        self.screen.blit(overlay, (0, 0))
        
        # Draw UI elements
        self.draw_title()
        self.draw_sections()
        
        for widget in self.all_widgets:
            if hasattr(widget, 'draw'):
                widget.draw(self.screen, self.scale)
        
        # Draw particles
        self.particles.draw(self.screen, self.scale)
        
        # Draw feedback message
        if self.feedback["timer"] > 0:
            font = pygame.font.Font(None, self.scale.font_size(28))
            surf = font.render(self.feedback["text"], True, self.feedback["color"])
            rect = surf.get_rect(center=(self.scale.screen_width//2, 
                                        self.scale.screen_height - self.scale.y(50)))
            bg = rect.inflate(self.scale.s(40), self.scale.s(20))
            pygame.draw.rect(self.screen, BLACK, bg)
            pygame.draw.rect(self.screen, self.feedback["color"], bg, max(1, self.scale.s(2)))
            self.screen.blit(surf, rect)
            
        # Fade in effect
        if self.fade < 255:
            fade = pygame.Surface((self.scale.screen_width, self.scale.screen_height))
            fade.fill(BLACK)
            fade.set_alpha(255 - self.fade)
            self.screen.blit(fade, (0, 0))
            
        pygame.display.flip()
        
    def run(self):
        while self.running:
            self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)
        return self.settings

def main():
    settings = SettingsScreen()
    final = settings.run()
    
    print("\n" + "="*60)
    print("GRID SURVIVAL - Settings Saved")
    print("="*60)
    for key, value in final.items():
        print(f"  {key:20}: {value}")
    print("="*60)
    
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()