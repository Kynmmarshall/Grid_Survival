"""
UI and HUD system for Grid Survival.
Displays score, timer, player status, and elimination screens.
Redesigned with polished panels, arcade fonts, urgency styling, and animations.
"""

import math
import pygame
from typing import List, Optional
from settings import (
    WINDOW_SIZE,
    FONT_PATH_HUD,
    FONT_SIZE_LABEL,
    FONT_SIZE_VALUE,
    FONT_SIZE_LARGE,
    TIMER_WARNING_THRESHOLD,
    HUD_PANEL_BG,
    HUD_PANEL_RADIUS,
    HUD_PANEL_BORDER_WIDTH,
    HUD_PANEL_PADDING_H,
    HUD_PANEL_PADDING_V,
    HUD_SCORE_BORDER_COLOR,
    HUD_TIMER_BORDER_COLOR,
    HUD_ALIVE_BORDER_COLOR_ALL,
    HUD_ALIVE_BORDER_COLOR_ONE,
    HUD_ALIVE_BORDER_COLOR_LAST,
    HUD_TIMER_URGENT_COLOR,
    HUD_VALUE_COLOR,
    HUD_LABEL_COLOR_SCORE,
    HUD_LABEL_COLOR_TIMER,
    HUD_LABEL_COLOR_ALIVE,
    SCORE_ANIM_SCALE_UP_DURATION,
    SCORE_ANIM_SCALE_DOWN_DURATION,
)


# ─────────────────────────────────────────────────────────────────────────────
# Font loader helper
# ─────────────────────────────────────────────────────────────────────────────

def _load_font(path: str, size: int, bold: bool = False) -> pygame.font.Font:
    """
    Try to load a TTF font from path; fall back to Consolas system font.
    """
    try:
        return pygame.font.Font(path, size)
    except (pygame.error, FileNotFoundError, OSError):
        return pygame.font.SysFont("consolas", size, bold=bold)


# ─────────────────────────────────────────────────────────────────────────────
# Rounded-rect panel helper
# ─────────────────────────────────────────────────────────────────────────────

def _draw_panel(surface: pygame.Surface,
                rect: pygame.Rect,
                bg_color: tuple,
                border_color: tuple,
                border_width: int = 2,
                radius: int = 12,
                glow: bool = False):
    """
    Draw a dark semi-transparent rounded rectangle panel with a colored border
    and optional inner glow.
    """
    # Background
    bg_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(bg_surf, bg_color, bg_surf.get_rect(), border_radius=radius)
    surface.blit(bg_surf, rect.topleft)

    # Outer border
    pygame.draw.rect(surface, border_color, rect, border_width, border_radius=radius)

    # Inner glow (1px inside border, lighter shade)
    if glow:
        inner_rect = rect.inflate(-border_width * 2, -border_width * 2)
        glow_color = tuple(min(255, c + 60) for c in border_color[:3])
        pygame.draw.rect(surface, glow_color, inner_rect, 1, border_radius=max(1, radius - border_width))


# ─────────────────────────────────────────────────────────────────────────────
# GameHUD
# ─────────────────────────────────────────────────────────────────────────────

class GameHUD:
    """Heads-up display showing game stats and player info."""

    def __init__(self):
        # Load fonts once at startup
        self._font_label = _load_font(FONT_PATH_HUD, FONT_SIZE_LABEL)
        self._font_value = _load_font(FONT_PATH_HUD, FONT_SIZE_VALUE, bold=True)
        self._font_large = _load_font(FONT_PATH_HUD, FONT_SIZE_LARGE, bold=True)

        self.survival_time = 0.0
        self.score = 0
        self._prev_score = 0
        self.player_name = "Player"
        self.players_alive = 1
        self.total_players = 1
        self.player_health = 0
        self.player_max_health = 0
        self.current_level = 1
        self.level_name = ""

        # Score animation state
        self._score_anim_timer = 0.0
        self._score_anim_phase = "idle"   # "up" | "down" | "idle"
        self._score_scale = 1.0
        self._score_flash = False

        # Timer urgency pulse
        self._pulse_timer = 0.0

    def update(self, dt: float):
        """Update HUD state."""
        self.survival_time += dt
        new_score = int(self.survival_time * 10)

        if new_score != self.score:
            self.score = new_score
            if new_score > self._prev_score:
                self._start_score_anim()
            self._prev_score = new_score

        # Update score animation
        self._update_score_anim(dt)

        # Timer urgency pulse
        self._pulse_timer += dt

    def _start_score_anim(self):
        self._score_anim_phase = "up"
        self._score_anim_timer = 0.0
        self._score_flash = True

    def _update_score_anim(self, dt: float):
        if self._score_anim_phase == "up":
            self._score_anim_timer += dt
            t = min(1.0, self._score_anim_timer / SCORE_ANIM_SCALE_UP_DURATION)
            self._score_scale = 1.0 + 0.2 * t
            if self._score_anim_timer >= SCORE_ANIM_SCALE_UP_DURATION:
                self._score_anim_phase = "down"
                self._score_anim_timer = 0.0
                self._score_flash = False
        elif self._score_anim_phase == "down":
            self._score_anim_timer += dt
            t = min(1.0, self._score_anim_timer / SCORE_ANIM_SCALE_DOWN_DURATION)
            self._score_scale = 1.2 - 0.2 * t
            if self._score_anim_timer >= SCORE_ANIM_SCALE_DOWN_DURATION:
                self._score_anim_phase = "idle"
                self._score_scale = 1.0
        else:
            self._score_scale = 1.0

    def _alive_color(self) -> tuple:
        """Return the alive counter color based on remaining players."""
        if self.total_players <= 1:
            return HUD_ALIVE_BORDER_COLOR_ALL
        eliminated = self.total_players - self.players_alive
        if eliminated == 0:
            return HUD_ALIVE_BORDER_COLOR_ALL
        elif self.players_alive == 1:
            return HUD_ALIVE_BORDER_COLOR_LAST
        else:
            return HUD_ALIVE_BORDER_COLOR_ONE

    def _is_timer_urgent(self) -> bool:
        """True when survival time is in the last TIMER_WARNING_THRESHOLD seconds
        of a hypothetical game limit, or simply always after a long time."""
        # We use it as: urgent when time is a multiple of warning threshold
        # In practice: urgent after 60s (arbitrary) — adapt as needed.
        # For now: urgent when time > 60s and in last 10s of each minute.
        remaining_in_minute = 60 - (self.survival_time % 60)
        return remaining_in_minute <= TIMER_WARNING_THRESHOLD

    def draw(self, surface: pygame.Surface):
        """Draw HUD elements."""
        self._draw_score_panel(surface)
        self._draw_timer_panel(surface)
        # Show level info
        if self.level_name:
            self._draw_level_panel(surface)
        # Show health if player has health points
        if self.player_max_health > 0:
            self._draw_health_panel(surface)
        if self.total_players > 1:
            self._draw_alive_panel(surface)

    def _draw_score_panel(self, surface: pygame.Surface):
        """Score panel — top-left."""
        label_surf = self._font_label.render("SCORE", True, HUD_LABEL_COLOR_SCORE)

        # Animated score value
        score_str = str(self.score)
        if self._score_flash:
            value_color = HUD_SCORE_BORDER_COLOR  # GOLD flash
        else:
            value_color = HUD_VALUE_COLOR

        value_surf = self._font_value.render(score_str, True, value_color)

        # Scale the value surface
        if self._score_scale != 1.0:
            w = max(1, int(value_surf.get_width() * self._score_scale))
            h = max(1, int(value_surf.get_height() * self._score_scale))
            value_surf = pygame.transform.smoothscale(value_surf, (w, h))

        panel_w = max(label_surf.get_width(), value_surf.get_width()) + HUD_PANEL_PADDING_H * 2
        panel_h = label_surf.get_height() + value_surf.get_height() + HUD_PANEL_PADDING_V * 3
        panel_rect = pygame.Rect(20, 20, panel_w, panel_h)

        _draw_panel(surface, panel_rect, HUD_PANEL_BG, HUD_SCORE_BORDER_COLOR,
                    HUD_PANEL_BORDER_WIDTH, HUD_PANEL_RADIUS, glow=True)

        # Label centered at top of panel
        lx = panel_rect.centerx - label_surf.get_width() // 2
        ly = panel_rect.top + HUD_PANEL_PADDING_V
        surface.blit(label_surf, (lx, ly))

        # Value centered below label
        vx = panel_rect.centerx - value_surf.get_width() // 2
        vy = ly + label_surf.get_height() + HUD_PANEL_PADDING_V
        surface.blit(value_surf, (vx, vy))

    def _draw_timer_panel(self, surface: pygame.Surface):
        """Timer panel — top-center."""
        urgent = self._is_timer_urgent()

        minutes = int(self.survival_time // 60)
        seconds = int(self.survival_time % 60)
        time_str = f"{minutes:02d}:{seconds:02d}"

        label_surf = self._font_label.render("TIME", True, HUD_LABEL_COLOR_TIMER)

        if urgent:
            # Pulse: border and text go red, font size increases
            pulse = 0.5 + 0.5 * math.sin(self._pulse_timer * math.pi * 4)
            border_color = HUD_TIMER_URGENT_COLOR
            value_color = HUD_TIMER_URGENT_COLOR
            value_surf = self._font_large.render(time_str, True, value_color)
            # Flash background darker on pulse
            bg_alpha = int(180 + 60 * pulse)
            bg_color = (20, 20, 20, bg_alpha)
        else:
            border_color = HUD_TIMER_BORDER_COLOR
            value_color = HUD_VALUE_COLOR
            value_surf = self._font_value.render(time_str, True, value_color)
            bg_color = HUD_PANEL_BG

        panel_w = max(label_surf.get_width(), value_surf.get_width()) + HUD_PANEL_PADDING_H * 2
        panel_h = label_surf.get_height() + value_surf.get_height() + HUD_PANEL_PADDING_V * 3
        panel_rect = pygame.Rect(0, 20, panel_w, panel_h)
        panel_rect.centerx = WINDOW_SIZE[0] // 2

        _draw_panel(surface, panel_rect, bg_color, border_color,
                    HUD_PANEL_BORDER_WIDTH, HUD_PANEL_RADIUS, glow=True)

        lx = panel_rect.centerx - label_surf.get_width() // 2
        ly = panel_rect.top + HUD_PANEL_PADDING_V
        surface.blit(label_surf, (lx, ly))

        vx = panel_rect.centerx - value_surf.get_width() // 2
        vy = ly + label_surf.get_height() + HUD_PANEL_PADDING_V
        surface.blit(value_surf, (vx, vy))

    def _draw_alive_panel(self, surface: pygame.Surface):
        """Alive counter panel — top-right."""
        alive_color = self._alive_color()

        # Last player: slow pulse
        if self.players_alive == 1 and self.total_players > 1:
            pulse = 0.5 + 0.5 * math.sin(self._pulse_timer * math.pi * 1.5)
            border_color = tuple(int(c * (0.7 + 0.3 * pulse)) for c in alive_color)
        else:
            border_color = alive_color

        label_surf = self._font_label.render("ALIVE", True, alive_color)
        value_str = f"{self.players_alive}/{self.total_players}"
        value_surf = self._font_value.render(value_str, True, HUD_VALUE_COLOR)

        panel_w = max(label_surf.get_width(), value_surf.get_width()) + HUD_PANEL_PADDING_H * 2
        panel_h = label_surf.get_height() + value_surf.get_height() + HUD_PANEL_PADDING_V * 3
        panel_rect = pygame.Rect(0, 20, panel_w, panel_h)
        panel_rect.right = WINDOW_SIZE[0] - 20

        _draw_panel(surface, panel_rect, HUD_PANEL_BG, border_color,
                    HUD_PANEL_BORDER_WIDTH, HUD_PANEL_RADIUS, glow=True)

        lx = panel_rect.centerx - label_surf.get_width() // 2
        ly = panel_rect.top + HUD_PANEL_PADDING_V
        surface.blit(label_surf, (lx, ly))

        vx = panel_rect.centerx - value_surf.get_width() // 2
        vy = ly + label_surf.get_height() + HUD_PANEL_PADDING_V
        surface.blit(value_surf, (vx, vy))

    def _draw_level_panel(self, surface: pygame.Surface):
        """Level panel — below timer on center."""
        level_color = (100, 150, 255)  # Blue for level

        label_surf = self._font_label.render("LEVEL", True, level_color)
        value_str = f"{self.current_level}"
        value_surf = self._font_value.render(value_str, True, HUD_VALUE_COLOR)

        # Level name below
        name_surf = _load_font(FONT_PATH_HUD, 14).render(self.level_name, True, (180, 180, 200))

        panel_w = max(label_surf.get_width(), value_surf.get_width(), name_surf.get_width()) + HUD_PANEL_PADDING_H * 2
        panel_h = label_surf.get_height() + value_surf.get_height() + name_surf.get_height() + HUD_PANEL_PADDING_V * 4
        panel_rect = pygame.Rect(0, 80, panel_w, panel_h)
        panel_rect.centerx = WINDOW_SIZE[0] // 2

        _draw_panel(surface, panel_rect, HUD_PANEL_BG, level_color,
                    HUD_PANEL_BORDER_WIDTH, HUD_PANEL_RADIUS, glow=True)

        lx = panel_rect.centerx - label_surf.get_width() // 2
        ly = panel_rect.top + HUD_PANEL_PADDING_V
        surface.blit(label_surf, (lx, ly))

        vx = panel_rect.centerx - value_surf.get_width() // 2
        vy = ly + label_surf.get_height() + HUD_PANEL_PADDING_V
        surface.blit(value_surf, (vx, vy))

        nx = panel_rect.centerx - name_surf.get_width() // 2
        ny = vy + value_surf.get_height() + HUD_PANEL_PADDING_V
        surface.blit(name_surf, (nx, ny))

    def _draw_health_panel(self, surface: pygame.Surface):
        """Health panel — below score panel on left."""
        health_color = (220, 50, 50)  # Red for health
        
        label_surf = self._font_label.render("HEALTH", True, health_color)
        value_str = f"{self.player_health}/{self.player_max_health}"
        value_surf = self._font_value.render(value_str, True, HUD_VALUE_COLOR)

        panel_w = max(label_surf.get_width(), value_surf.get_width()) + HUD_PANEL_PADDING_H * 2
        panel_h = label_surf.get_height() + value_surf.get_height() + HUD_PANEL_PADDING_V * 3
        panel_rect = pygame.Rect(20, 100, panel_w, panel_h)

        _draw_panel(surface, panel_rect, HUD_PANEL_BG, health_color,
                    HUD_PANEL_BORDER_WIDTH, HUD_PANEL_RADIUS, glow=True)

        lx = panel_rect.left + HUD_PANEL_PADDING_H
        ly = panel_rect.top + HUD_PANEL_PADDING_V
        surface.blit(label_surf, (lx, ly))

        vx = panel_rect.left + HUD_PANEL_PADDING_H
        vy = ly + label_surf.get_height() + HUD_PANEL_PADDING_V
        surface.blit(value_surf, (vx, vy))

    def reset(self):
        """Reset HUD state."""
        self.survival_time = 0.0
        self.score = 0
        self._prev_score = 0
        self._score_anim_phase = "idle"
        self._score_scale = 1.0
        self._score_flash = False
        self._pulse_timer = 0.0
        self.player_health = 0
        self.player_max_health = 0
        self.current_level = 1
        self.level_name = ""

    def set_player_info(self, name: str, alive: int, total: int, health: int = 0, max_health: int = 0, level: int = 1, level_name: str = ""):
        """Update player information."""
        self.player_name = name
        self.players_alive = alive
        self.total_players = total
        self.player_health = health
        self.player_max_health = max_health
        self.current_level = level
        self.level_name = level_name


# ─────────────────────────────────────────────────────────────────────────────
# EliminationScreen
# ─────────────────────────────────────────────────────────────────────────────

class EliminationScreen:
    """Screen shown when player is eliminated."""

    def __init__(self, player_name: str, survival_time: float, score: int, reason: str = "eliminated"):
        self.player_name = player_name
        self.survival_time = survival_time
        self.score = score
        self.reason = reason

        # Use the same HUD font hierarchy — fits within screen width
        self.font_title = _load_font(FONT_PATH_HUD, 42, bold=True)
        self.font_large = _load_font(FONT_PATH_HUD, 28, bold=True)
        self.font_medium = _load_font(FONT_PATH_HUD, 20)
        self.font_small = _load_font(FONT_PATH_HUD, 14)

        self.alpha = 0
        self.fade_speed = 300
        self.visible = False
        self._time = 0.0

    def show(self):
        self.visible = True
        self.alpha = 0
        self._time = 0.0

    def update(self, dt: float):
        if self.visible and self.alpha < 255:
            self.alpha = min(255, self.alpha + self.fade_speed * dt)
        self._time += dt

    def draw(self, surface: pygame.Surface):
        if not self.visible:
            return

        # Dark overlay
        overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(self.alpha * 0.75)))
        surface.blit(overlay, (0, 0))

        if self.alpha < 80:
            return

        text_alpha = min(255, int((self.alpha - 80) * 1.8))
        cx = WINDOW_SIZE[0] // 2

        # ── Title ──────────────────────────────────────────────────────────
        title_text = "ELIMINATED!" if self.reason == "eliminated" else "GAME OVER!"
        title_color = (255, 60, 60)

        # Pulse the title color red/orange
        pulse = 0.5 + 0.5 * math.sin(self._time * math.pi * 3)
        r = int(255)
        g = int(60 + 80 * pulse)
        title_color = (r, g, 60)

        title_surf = self.font_title.render(title_text, True, title_color)
        # Scale down if wider than 80% of screen
        max_w = int(WINDOW_SIZE[0] * 0.80)
        if title_surf.get_width() > max_w:
            scale = max_w / title_surf.get_width()
            new_w = max(1, int(title_surf.get_width() * scale))
            new_h = max(1, int(title_surf.get_height() * scale))
            title_surf = pygame.transform.smoothscale(title_surf, (new_w, new_h))
        title_surf.set_alpha(text_alpha)

        # Draw drop shadow
        shadow_surf = self.font_title.render(title_text, True, (0, 0, 0))
        if shadow_surf.get_width() > max_w:
            shadow_surf = pygame.transform.smoothscale(shadow_surf, title_surf.get_size())
        shadow_surf.set_alpha(int(text_alpha * 0.5))
        shadow_rect = shadow_surf.get_rect(center=(cx + 3, 163))
        surface.blit(shadow_surf, shadow_rect)

        title_rect = title_surf.get_rect(center=(cx, 160))
        surface.blit(title_surf, title_rect)

        # ── Panel card ─────────────────────────────────────────────────────
        panel_w = 520
        panel_h = 260
        panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
        panel_rect.center = (cx, WINDOW_SIZE[1] // 2 + 30)

        panel_alpha = min(255, text_alpha)
        _draw_panel(surface, panel_rect, (15, 15, 25, panel_alpha),
                    (255, 60, 60), 2, 14, glow=True)

        # Player name
        name_surf = self.font_large.render(self.player_name, True, (255, 255, 255))
        name_surf.set_alpha(text_alpha)
        surface.blit(name_surf, name_surf.get_rect(center=(cx, panel_rect.top + 45)))

        # Divider line — draw.line ignores alpha on non-SRCALPHA surfaces,
        # so render the line on a temporary surface and blit with set_alpha.
        div_y = panel_rect.top + 75
        div_surf = pygame.Surface((panel_rect.width - 40, 1), pygame.SRCALPHA)
        div_surf.fill((255, 60, 60, text_alpha))
        surface.blit(div_surf, (panel_rect.left + 20, div_y))

        # Survived time
        minutes = int(self.survival_time // 60)
        seconds = int(self.survival_time % 60)
        time_text = f"Survived:  {minutes:02d}:{seconds:02d}"
        time_surf = self.font_medium.render(time_text, True, (180, 200, 255))
        time_surf.set_alpha(text_alpha)
        surface.blit(time_surf, time_surf.get_rect(center=(cx, panel_rect.top + 115)))

        # Final score
        score_text = f"Final Score:  {self.score}"
        score_surf = self.font_medium.render(score_text, True, (255, 210, 80))
        score_surf.set_alpha(text_alpha)
        surface.blit(score_surf, score_surf.get_rect(center=(cx, panel_rect.top + 155)))

        # Restart prompt (blinks after fully faded in)
        if self.alpha >= 220:
            blink_alpha = int(120 + 135 * abs(math.sin(self._time * math.pi * 1.5)))
            restart_surf = self.font_small.render(
                "Press  R  to Restart    |    Press  ESC  to Quit",
                True, (180, 180, 180)
            )
            restart_surf.set_alpha(blink_alpha)
            surface.blit(restart_surf, restart_surf.get_rect(center=(cx, panel_rect.top + 220)))


# ─────────────────────────────────────────────────────────────────────────────
# VictoryScreen
# ─────────────────────────────────────────────────────────────────────────────

class VictoryScreen:
    """Screen shown when player wins (survives longest in multiplayer)."""

    def __init__(self, player_name: str, survival_time: float, score: int):
        self.player_name = player_name
        self.survival_time = survival_time
        self.score = score

        self.font_title = _load_font(FONT_PATH_HUD, 42, bold=True)
        self.font_large = _load_font(FONT_PATH_HUD, 28, bold=True)
        self.font_medium = _load_font(FONT_PATH_HUD, 20)
        self.font_small = _load_font(FONT_PATH_HUD, 14)

        self.alpha = 0
        self.fade_speed = 300
        self.visible = False
        self._time = 0.0

    def show(self):
        self.visible = True
        self.alpha = 0
        self._time = 0.0

    def update(self, dt: float):
        if self.visible and self.alpha < 255:
            self.alpha = min(255, self.alpha + self.fade_speed * dt)
        self._time += dt

    def draw(self, surface: pygame.Surface):
        if not self.visible:
            return

        overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, int(self.alpha * 0.75)))
        surface.blit(overlay, (0, 0))

        if self.alpha < 80:
            return

        text_alpha = min(255, int((self.alpha - 80) * 1.8))
        cx = WINDOW_SIZE[0] // 2

        # ── Title ──────────────────────────────────────────────────────────
        pulse = 0.5 + 0.5 * math.sin(self._time * math.pi * 2.5)
        g = int(200 + 55 * pulse)
        title_color = (80, g, 80)

        title_surf = self.font_title.render("VICTORY!", True, title_color)
        max_w = int(WINDOW_SIZE[0] * 0.80)
        if title_surf.get_width() > max_w:
            scale = max_w / title_surf.get_width()
            title_surf = pygame.transform.smoothscale(
                title_surf,
                (max(1, int(title_surf.get_width() * scale)),
                 max(1, int(title_surf.get_height() * scale)))
            )
        title_surf.set_alpha(text_alpha)

        shadow_surf = self.font_title.render("VICTORY!", True, (0, 0, 0))
        if shadow_surf.get_width() > max_w:
            shadow_surf = pygame.transform.smoothscale(shadow_surf, title_surf.get_size())
        shadow_surf.set_alpha(int(text_alpha * 0.5))
        surface.blit(shadow_surf, shadow_surf.get_rect(center=(cx + 3, 163)))
        surface.blit(title_surf, title_surf.get_rect(center=(cx, 160)))

        # ── Panel card ─────────────────────────────────────────────────────
        panel_w = 520
        panel_h = 260
        panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
        panel_rect.center = (cx, WINDOW_SIZE[1] // 2 + 30)

        _draw_panel(surface, panel_rect, (15, 25, 15, min(255, text_alpha)),
                    (80, 220, 80), 2, 14, glow=True)

        name_surf = self.font_large.render(self.player_name, True, (255, 255, 255))
        name_surf.set_alpha(text_alpha)
        surface.blit(name_surf, name_surf.get_rect(center=(cx, panel_rect.top + 45)))

        div_y = panel_rect.top + 75
        pygame.draw.line(surface, (80, 220, 80),
                         (panel_rect.left + 20, div_y), (panel_rect.right - 20, div_y), 1)

        minutes = int(self.survival_time // 60)
        seconds = int(self.survival_time % 60)
        time_text = f"Survived:  {minutes:02d}:{seconds:02d}"
        time_surf = self.font_medium.render(time_text, True, (180, 200, 255))
        time_surf.set_alpha(text_alpha)
        surface.blit(time_surf, time_surf.get_rect(center=(cx, panel_rect.top + 115)))

        score_text = f"Final Score:  {self.score}"
        score_surf = self.font_medium.render(score_text, True, (255, 210, 80))
        score_surf.set_alpha(text_alpha)
        surface.blit(score_surf, score_surf.get_rect(center=(cx, panel_rect.top + 155)))

        if self.alpha >= 220:
            blink_alpha = int(120 + 135 * abs(math.sin(self._time * math.pi * 1.5)))
            restart_surf = self.font_small.render(
                "Press  R  to Restart    |    Press  ESC  to Quit",
                True, (180, 180, 180)
            )
            restart_surf.set_alpha(blink_alpha)
            surface.blit(restart_surf, restart_surf.get_rect(center=(cx, panel_rect.top + 220)))