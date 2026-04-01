"""
UI and HUD system for Grid Survival.
Displays timer, player status, and elimination screens.
Redesigned with polished panels, arcade fonts, urgency styling, and animations.
"""

import math
import pygame
from typing import List
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
    HUD_TIMER_BORDER_COLOR,
    HUD_ALIVE_BORDER_COLOR_ALL,
    HUD_ALIVE_BORDER_COLOR_ONE,
    HUD_ALIVE_BORDER_COLOR_LAST,
    HUD_TIMER_URGENT_COLOR,
    HUD_VALUE_COLOR,
    HUD_LABEL_COLOR_TIMER,
    HUD_LABEL_COLOR_ALIVE,
)
from playercard import PlayerCardRenderer


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
        self._font_card_small = _load_font(FONT_PATH_HUD, max(10, FONT_SIZE_LABEL - 2))
        self._player_cards = PlayerCardRenderer(self._font_card_small, _draw_panel)

        self.survival_time = 0.0
        self.player_name = "Player"
        self.players_alive = 1
        self.total_players = 1

        # Timer urgency pulse
        self._pulse_timer = 0.0

        self.mute_rect = None   # Mute button hit area

    def update(self, dt: float):
        """Update HUD state."""
        self.survival_time += dt

        # Timer urgency pulse
        self._pulse_timer += dt

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

    def draw(self, surface: pygame.Surface, players: List, is_muted: bool = False):
        """Draw HUD elements."""
        self._draw_timer_panel(surface)
        self._draw_mute_button(surface, is_muted)
        self._draw_player_cards(surface, players)
        if self.total_players > 1:
            self._draw_alive_panel(surface)

    def _draw_mute_button(self, surface: pygame.Surface, is_muted: bool):
        """Draw a clickable mute button."""
        label = "MUTED" if is_muted else "AUDIO"
        # Use existing colors: Red for muted, Green for active
        color = HUD_TIMER_URGENT_COLOR if is_muted else HUD_ALIVE_BORDER_COLOR_ALL

        label_surf = self._font_label.render(label, True, color)

        panel_w = label_surf.get_width() + HUD_PANEL_PADDING_H * 2
        panel_h = label_surf.get_height() + HUD_PANEL_PADDING_V * 2
        
        # Keep the audio control out of the top edge so it stays clear of the player cards.
        self.mute_rect = pygame.Rect(20, WINDOW_SIZE[1] - panel_h - 20, panel_w, panel_h)

        _draw_panel(surface, self.mute_rect, HUD_PANEL_BG, color,
                    HUD_PANEL_BORDER_WIDTH, 8, glow=False)

        lx = self.mute_rect.centerx - label_surf.get_width() // 2
        ly = self.mute_rect.centery - label_surf.get_height() // 2
        surface.blit(label_surf, (lx, ly))

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
        """Alive counter panel — bottom-right."""
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
        panel_rect = pygame.Rect(0, 0, panel_w, panel_h)
        panel_rect.right = WINDOW_SIZE[0] - 20
        panel_rect.bottom = WINDOW_SIZE[1] - 20

        _draw_panel(surface, panel_rect, HUD_PANEL_BG, border_color,
                    HUD_PANEL_BORDER_WIDTH, HUD_PANEL_RADIUS, glow=True)

        lx = panel_rect.centerx - label_surf.get_width() // 2
        ly = panel_rect.top + HUD_PANEL_PADDING_V
        surface.blit(label_surf, (lx, ly))

        vx = panel_rect.centerx - value_surf.get_width() // 2
        vy = ly + label_surf.get_height() + HUD_PANEL_PADDING_V
        surface.blit(value_surf, (vx, vy))

    def _draw_player_cards(self, surface: pygame.Surface, players: List):
        self._player_cards.draw(surface, players)

    def reset(self):
        """Reset HUD state."""
        self.survival_time = 0.0
        self._pulse_timer = 0.0

    def set_player_info(self, name: str, alive: int, total: int):
        """Update player information."""
        self.player_name = name
        self.players_alive = alive
        self.total_players = total


# ─────────────────────────────────────────────────────────────────────────────
# EliminationScreen
# ─────────────────────────────────────────────────────────────────────────────

class EliminationScreen:
    """Screen shown when player is eliminated."""

    def __init__(self, player_name: str, survival_time: float, reason: str = "eliminated"):
        self.player_name = player_name
        self.survival_time = survival_time
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

        # Divider line
        div_y = panel_rect.top + 75
        pygame.draw.line(surface, (255, 60, 60, text_alpha),
                         (panel_rect.left + 20, div_y), (panel_rect.right - 20, div_y), 1)

        # Survived time
        minutes = int(self.survival_time // 60)
        seconds = int(self.survival_time % 60)
        time_text = f"Survived:  {minutes:02d}:{seconds:02d}"
        time_surf = self.font_medium.render(time_text, True, (180, 200, 255))
        time_surf.set_alpha(text_alpha)
        surface.blit(time_surf, time_surf.get_rect(center=(cx, panel_rect.top + 115)))

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

    def __init__(self, player_name: str, survival_time: float):
        self.player_name = player_name
        self.survival_time = survival_time

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

        if self.alpha >= 220:
            blink_alpha = int(120 + 135 * abs(math.sin(self._time * math.pi * 1.5)))
            restart_surf = self.font_small.render(
                "Press  R  to Restart    |    Press  ESC  to Quit",
                True, (180, 180, 180)
            )
            restart_surf.set_alpha(blink_alpha)
            surface.blit(restart_surf, restart_surf.get_rect(center=(cx, panel_rect.top + 220)))
