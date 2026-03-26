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
    POWER_ORBS_REQUIRED,
)

ORB_ICON_COLORS = {
    "Speed Boost": (60, 230, 220),
    "Shield": (255, 210, 50),
    "Frozen": (90, 150, 255),
    "Power Charge": (200, 80, 255),
    "Bomb Detonation": (255, 90, 70),
}
CARD_TIMER_BG = (30, 30, 45)
CARD_TIMER_FILL = (255, 200, 80)
CARD_TIMER_BORDER = (55, 55, 70)


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

        self.survival_time = 0.0
        self.score = 0
        self._prev_score = 0
        self.player_name = "Player"
        self.players_alive = 1
        self.total_players = 1

        # Score animation state
        self._score_anim_timer = 0.0
        self._score_anim_phase = "idle"   # "up" | "down" | "idle"
        self._score_scale = 1.0
        self._score_flash = False

        # Timer urgency pulse
        self._pulse_timer = 0.0

        self.mute_rect = None   # Mute button hit area

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

    def draw(self, surface: pygame.Surface, players: List, is_muted: bool = False):
        """Draw HUD elements."""
        self._draw_score_panel(surface)
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
        
        # Position below Score panel (Score is at 20, 20 with height ~80-100)
        # Let's put it at (20, 110)
        self.mute_rect = pygame.Rect(20, 110, panel_w, panel_h)

        _draw_panel(surface, self.mute_rect, HUD_PANEL_BG, color,
                    HUD_PANEL_BORDER_WIDTH, 8, glow=False)

        lx = self.mute_rect.centerx - label_surf.get_width() // 2
        ly = self.mute_rect.centery - label_surf.get_height() // 2
        surface.blit(label_surf, (lx, ly))

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

    def _draw_player_cards(self, surface: pygame.Surface, players: List):
        if not players:
            return
        active_players = [p for p in players if not getattr(p, '_eliminated', False)]
        render_players = active_players or players
        card_w, card_h = 260, 120
        rects = self._player_card_rects(len(render_players), card_w, card_h)
        palette = [
            (255, 200, 0),
            (80, 220, 255),
            (255, 120, 140),
            (140, 255, 160),
        ]
        for idx, player in enumerate(render_players):
            if idx >= len(rects):
                break
            color = palette[idx % len(palette)]
            self._draw_player_card(surface, rects[idx], player, idx, color)

    def _player_card_rects(self, count: int, width: int, height: int) -> List[pygame.Rect]:
        margin = 20
        top_y = 160
        bottom_y = WINDOW_SIZE[1] - height - margin
        anchors = [
            (margin, top_y),
            (WINDOW_SIZE[0] - width - margin, top_y),
            (margin, bottom_y),
            (WINDOW_SIZE[0] - width - margin, bottom_y),
        ]
        rects: List[pygame.Rect] = []
        if count <= len(anchors):
            for idx in range(count):
                x, y = anchors[idx]
                rects.append(pygame.Rect(x, y, width, height))
            return rects

        columns = min(3, count)
        spacing_x = (WINDOW_SIZE[0] - 2 * margin - width) / max(1, columns - 1)
        rows = math.ceil(count / columns)
        positions_y = [top_y, bottom_y]
        for row in range(rows):
            y = positions_y[row % len(positions_y)] if rows > 1 else top_y
            for col in range(columns):
                idx = row * columns + col
                if idx >= count:
                    break
                x = int(margin + col * spacing_x)
                rects.append(pygame.Rect(x, y, width, height))
        return rects

    def _draw_player_card(self, surface: pygame.Surface, rect: pygame.Rect,
                           player, index: int, border_color: tuple):
        if player is None:
            return
        _draw_panel(surface, rect, HUD_PANEL_BG, border_color,
                    HUD_PANEL_BORDER_WIDTH, HUD_PANEL_RADIUS, glow=True)

        portrait = self._headshot_surface(player, 70, border_color)
        portrait_rect = portrait.get_rect()
        portrait_rect.topleft = (rect.left + 14, rect.top + 12)
        surface.blit(portrait, portrait_rect)

        text_x = portrait_rect.right + 12
        text_y = rect.top + 12
        label = self._font_card_small.render(f"P{index + 1}", True, border_color)
        surface.blit(label, (text_x, text_y))
        name = getattr(player, "character_name", "Unknown")
        name_surf = self._font_card_small.render(name, True, HUD_VALUE_COLOR)
        surface.blit(name_surf, (text_x + label.get_width() + 8, text_y))

        icon_y = rect.top + 56
        power_color = getattr(getattr(player, "power", None), "COLOR", border_color)
        self._draw_power_icon(surface, (text_x + 18, icon_y), power_color)

        charges = getattr(player, "power_orb_charges", 0)
        self._draw_charge_pips(surface, (text_x + 68, icon_y), charges, border_color)

        orb_label = None
        orb_timer = 0.0
        orb_infinite = False
        orb_duration = 0.0
        if hasattr(player, "get_active_orb_status"):
            status = player.get_active_orb_status()
            if status:
                orb_label, orb_timer, orb_infinite, orb_duration = status
        orb_color = self._orb_color_for_label(orb_label)
        self._draw_orb_icon(surface, (text_x + 130, icon_y), orb_color, bool(orb_label))

        self._draw_orb_timer_line(surface, rect, orb_color, orb_label,
                                  orb_timer, orb_infinite, orb_duration)

    def _headshot_surface(self, player, size: int, border_color: tuple) -> pygame.Surface:
        portrait = pygame.Surface((size, size), pygame.SRCALPHA)
        frame = getattr(getattr(player, "current_animation", None), "image", None)
        if frame:
            crop_height = max(1, int(frame.get_height() * 0.45))
            head_rect = pygame.Rect(0, 0, frame.get_width(), crop_height)
            head = frame.subsurface(head_rect).copy()
            head = pygame.transform.smoothscale(head, (size, size))
        else:
            head = pygame.Surface((size, size), pygame.SRCALPHA)
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (size // 2, size // 2), size // 2)
        head.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        portrait.blit(head, (0, 0))
        pygame.draw.circle(portrait, border_color, (size // 2, size // 2), size // 2, 2)
        return portrait

    def _draw_power_icon(self, surface: pygame.Surface, center: tuple[int, int], color: tuple):
        radius = 14
        icon = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        cx = cy = radius
        points = [
            (cx, cy - radius),
            (cx + radius, cy),
            (cx, cy + radius),
            (cx - radius, cy),
        ]
        pygame.draw.polygon(icon, color, points)
        pygame.draw.polygon(icon, (255, 255, 255, 120), points, 2)
        surface.blit(icon, icon.get_rect(center=center))

    def _draw_charge_pips(self, surface: pygame.Surface, origin: tuple[int, int],
                          charges: int, accent_color: tuple):
        required = max(1, POWER_ORBS_REQUIRED)
        radius = 6
        spacing = radius * 2 + 6
        start_x = origin[0]
        y = origin[1]
        for idx in range(required):
            cx = start_x + idx * spacing
            filled = idx < charges
            color = accent_color if filled else (80, 80, 90)
            pygame.draw.circle(surface, color, (cx, y), radius)
            pygame.draw.circle(surface, (255, 255, 255, 60), (cx, y), radius, 1)

    def _orb_color_for_label(self, label: Optional[str]) -> tuple:
        if not label:
            return (110, 110, 130)
        return ORB_ICON_COLORS.get(label, (200, 200, 220))

    def _draw_orb_icon(self, surface: pygame.Surface, center: tuple[int, int],
                       color: tuple, active: bool):
        radius = 14
        orb = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        fill_color = color if active else (55, 55, 70)
        pygame.draw.circle(orb, fill_color, (radius, radius), radius)
        pygame.draw.circle(orb, (255, 255, 255, 90), (radius - 4, radius - 6), radius // 2)
        pygame.draw.circle(orb, (255, 255, 255, 140), (radius, radius), radius, 2)
        surface.blit(orb, orb.get_rect(center=center))

    def _draw_orb_timer_line(self, surface: pygame.Surface, rect: pygame.Rect,
                              color: tuple, label: Optional[str], timer: float,
                              indefinite: bool, duration: float):
        line_rect = pygame.Rect(rect.left + 16, rect.bottom - 12, rect.width - 32, 6)
        pygame.draw.rect(surface, CARD_TIMER_BORDER, line_rect, border_radius=3)
        inner = line_rect.inflate(-2, -2)
        pygame.draw.rect(surface, CARD_TIMER_BG, inner, border_radius=3)

        if not label:
            return
        if indefinite or duration <= 0:
            pygame.draw.rect(surface, color or CARD_TIMER_FILL, inner, border_radius=3)
            return
        if timer <= 0:
            return
        progress = max(0.0, min(1.0, timer / duration))
        fill_width = max(2, int(inner.width * progress))
        fill_rect = pygame.Rect(inner.left, inner.top, fill_width, inner.height)
        pygame.draw.rect(surface, color or CARD_TIMER_FILL, fill_rect, border_radius=3)

    def reset(self):
        """Reset HUD state."""
        self.survival_time = 0.0
        self.score = 0
        self._prev_score = 0
        self._score_anim_phase = "idle"
        self._score_scale = 1.0
        self._score_flash = False
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
