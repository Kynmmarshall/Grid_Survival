"""
UI and HUD system for Grid Survival.
Displays score, timer, player status, and elimination screens.
"""

import pygame
from typing import List, Optional
from settings import WINDOW_SIZE


class GameHUD:
    """Heads-up display showing game stats and player info."""
    
    def __init__(self):
        self.font_large = pygame.font.SysFont("consolas", 48, bold=True)
        self.font_medium = pygame.font.SysFont("consolas", 32, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 24)
        
        self.survival_time = 0.0
        self.score = 0
        self.player_name = "Player"
        self.players_alive = 1
        self.total_players = 1
    
    def update(self, dt: float):
        """Update HUD state."""
        self.survival_time += dt
        # Score increases with survival time
        self.score = int(self.survival_time * 10)
    
    def draw(self, surface: pygame.Surface):
        """Draw HUD elements."""
        # Draw timer (top center)
        minutes = int(self.survival_time // 60)
        seconds = int(self.survival_time % 60)
        time_text = f"{minutes:02d}:{seconds:02d}"
        time_surface = self.font_large.render(time_text, True, (255, 255, 255))
        time_rect = time_surface.get_rect(midtop=(WINDOW_SIZE[0] // 2, 10))
        
        # Draw background for timer
        bg_rect = time_rect.inflate(20, 10)
        bg_surface = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(bg_surface, (0, 0, 0, 180), bg_surface.get_rect(), border_radius=10)
        surface.blit(bg_surface, bg_rect.topleft)
        surface.blit(time_surface, time_rect)
        
        # Draw score (top left)
        score_text = f"Score: {self.score}"
        score_surface = self.font_medium.render(score_text, True, (255, 220, 100))
        score_rect = score_surface.get_rect(topleft=(20, 20))
        
        bg_rect = score_rect.inflate(20, 10)
        bg_surface = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(bg_surface, (0, 0, 0, 180), bg_surface.get_rect(), border_radius=8)
        surface.blit(bg_surface, bg_rect.topleft)
        surface.blit(score_surface, score_rect)
        
        # Draw player status (top right)
        if self.total_players > 1:
            status_text = f"Alive: {self.players_alive}/{self.total_players}"
            status_surface = self.font_medium.render(status_text, True, (100, 255, 100))
            status_rect = status_surface.get_rect(topright=(WINDOW_SIZE[0] - 20, 20))
            
            bg_rect = status_rect.inflate(20, 10)
            bg_surface = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(bg_surface, (0, 0, 0, 180), bg_surface.get_rect(), border_radius=8)
            surface.blit(bg_surface, bg_rect.topleft)
            surface.blit(status_surface, status_rect)
    
    def reset(self):
        """Reset HUD state."""
        self.survival_time = 0.0
        self.score = 0
    
    def set_player_info(self, name: str, alive: int, total: int):
        """Update player information."""
        self.player_name = name
        self.players_alive = alive
        self.total_players = total


class EliminationScreen:
    """Screen shown when player is eliminated."""
    
    def __init__(self, player_name: str, survival_time: float, score: int, reason: str = "eliminated"):
        self.player_name = player_name
        self.survival_time = survival_time
        self.score = score
        self.reason = reason
        
        self.font_title = pygame.font.SysFont("impact", 72, bold=True)
        self.font_large = pygame.font.SysFont("consolas", 48, bold=True)
        self.font_medium = pygame.font.SysFont("consolas", 32)
        self.font_small = pygame.font.SysFont("consolas", 24)
        
        self.alpha = 0
        self.fade_speed = 300  # alpha per second
        self.visible = False
    
    def show(self):
        """Start showing the elimination screen."""
        self.visible = True
        self.alpha = 0
    
    def update(self, dt: float):
        """Update fade-in animation."""
        if self.visible and self.alpha < 255:
            self.alpha = min(255, self.alpha + self.fade_speed * dt)
    
    def draw(self, surface: pygame.Surface):
        """Draw elimination screen."""
        if not self.visible:
            return
        
        # Draw semi-transparent overlay
        overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(self.alpha * 0.7)))
        surface.blit(overlay, (0, 0))
        
        if self.alpha < 100:
            return
        
        # Calculate text alpha
        text_alpha = min(255, int((self.alpha - 100) * 1.5))
        
        # Draw "ELIMINATED" title
        title_text = "ELIMINATED!" if self.reason == "eliminated" else "GAME OVER!"
        title_color = (255, 50, 50, text_alpha)
        title_surface = self.font_title.render(title_text, True, (255, 50, 50))
        title_surface.set_alpha(text_alpha)
        title_rect = title_surface.get_rect(center=(WINDOW_SIZE[0] // 2, 150))
        surface.blit(title_surface, title_rect)
        
        # Draw player name
        name_surface = self.font_large.render(self.player_name, True, (255, 255, 255))
        name_surface.set_alpha(text_alpha)
        name_rect = name_surface.get_rect(center=(WINDOW_SIZE[0] // 2, 250))
        surface.blit(name_surface, name_rect)
        
        # Draw stats
        minutes = int(self.survival_time // 60)
        seconds = int(self.survival_time % 60)
        time_text = f"Survived: {minutes:02d}:{seconds:02d}"
        time_surface = self.font_medium.render(time_text, True, (200, 200, 255))
        time_surface.set_alpha(text_alpha)
        time_rect = time_surface.get_rect(center=(WINDOW_SIZE[0] // 2, 350))
        surface.blit(time_surface, time_rect)
        
        score_text = f"Final Score: {self.score}"
        score_surface = self.font_medium.render(score_text, True, (255, 220, 100))
        score_surface.set_alpha(text_alpha)
        score_rect = score_surface.get_rect(center=(WINDOW_SIZE[0] // 2, 400))
        surface.blit(score_surface, score_rect)
        
        # Draw instructions
        if self.alpha >= 255:
            restart_text = "Press R to Restart | Press ESC to Quit"
            restart_surface = self.font_small.render(restart_text, True, (180, 180, 180))
            restart_rect = restart_surface.get_rect(center=(WINDOW_SIZE[0] // 2, 500))
            surface.blit(restart_surface, restart_rect)


class VictoryScreen:
    """Screen shown when player wins (survives longest in multiplayer)."""
    
    def __init__(self, player_name: str, survival_time: float, score: int):
        self.player_name = player_name
        self.survival_time = survival_time
        self.score = score
        
        self.font_title = pygame.font.SysFont("impact", 72, bold=True)
        self.font_large = pygame.font.SysFont("consolas", 48, bold=True)
        self.font_medium = pygame.font.SysFont("consolas", 32)
        self.font_small = pygame.font.SysFont("consolas", 24)
        
        self.alpha = 0
        self.fade_speed = 300
        self.visible = False
    
    def show(self):
        """Start showing the victory screen."""
        self.visible = True
        self.alpha = 0
    
    def update(self, dt: float):
        """Update fade-in animation."""
        if self.visible and self.alpha < 255:
            self.alpha = min(255, self.alpha + self.fade_speed * dt)
    
    def draw(self, surface: pygame.Surface):
        """Draw victory screen."""
        if not self.visible:
            return
        
        # Draw semi-transparent overlay
        overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(self.alpha * 0.7)))
        surface.blit(overlay, (0, 0))
        
        if self.alpha < 100:
            return
        
        text_alpha = min(255, int((self.alpha - 100) * 1.5))
        
        # Draw "VICTORY" title
        title_surface = self.font_title.render("VICTORY!", True, (100, 255, 100))
        title_surface.set_alpha(text_alpha)
        title_rect = title_surface.get_rect(center=(WINDOW_SIZE[0] // 2, 150))
        surface.blit(title_surface, title_rect)
        
        # Draw player name
        name_surface = self.font_large.render(self.player_name, True, (255, 255, 255))
        name_surface.set_alpha(text_alpha)
        name_rect = name_surface.get_rect(center=(WINDOW_SIZE[0] // 2, 250))
        surface.blit(name_surface, name_rect)
        
        # Draw stats
        minutes = int(self.survival_time // 60)
        seconds = int(self.survival_time % 60)
        time_text = f"Survived: {minutes:02d}:{seconds:02d}"
        time_surface = self.font_medium.render(time_text, True, (200, 200, 255))
        time_surface.set_alpha(text_alpha)
        time_rect = time_surface.get_rect(center=(WINDOW_SIZE[0] // 2, 350))
        surface.blit(time_surface, time_rect)
        
        score_text = f"Final Score: {self.score}"
        score_surface = self.font_medium.render(score_text, True, (255, 220, 100))
        score_surface.set_alpha(text_alpha)
        score_rect = score_surface.get_rect(center=(WINDOW_SIZE[0] // 2, 400))
        surface.blit(score_surface, score_rect)
        
        # Draw instructions
        if self.alpha >= 255:
            restart_text = "Press R to Restart | Press ESC to Quit"
            restart_surface = self.font_small.render(restart_text, True, (180, 180, 180))
            restart_rect = restart_surface.get_rect(center=(WINDOW_SIZE[0] // 2, 500))
            surface.blit(restart_surface, restart_rect)
