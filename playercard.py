from __future__ import annotations

import math
from pathlib import Path
from typing import Callable, List, Optional

import pygame

from settings import (
    WINDOW_SIZE,
    HUD_PANEL_BG,
    HUD_PANEL_BORDER_WIDTH,
    HUD_PANEL_RADIUS,
    POWER_ORBS_REQUIRED,
    ORB_ICON_PATHS,
    PLAYER_PORTRAIT_DIR,
)

CARD_COLOR_PALETTE = [
    (255, 200, 0),
    (80, 220, 255),
    (255, 120, 140),
    (140, 255, 160),
]
CARD_TIMER_BG = (30, 30, 45)
CARD_TIMER_FILL = (255, 200, 80)
CARD_TIMER_BORDER = (55, 55, 70)
ORB_ICON_COLORS = {
    "speed boost": (60, 230, 220),
    "shield": (255, 210, 50),
    "frozen": (90, 150, 255),
    "void walk": (120, 255, 190),
    "power charge": (200, 80, 255),
}
ORB_LABEL_TO_KEY = {
    "speed boost": "speed",
    "shield": "shield",
    "frozen": "freeze",
    "void walk": "phase",
    "power charge": "power",
}

CARD_WIDTH = 282
CARD_HEIGHT = 164
CARD_MARGIN_X = 20
CARD_MARGIN_Y = 18
CARD_ROW_GAP = 58
CARD_STATUS_BG = (18, 22, 34, 220)
CARD_STATUS_BORDER = (92, 112, 150)
CARD_TEXT_DIM = (190, 200, 215)
CARD_TEXT_FAINT = (145, 155, 175)
CARD_WINS_BG = (16, 22, 36, 228)


class PlayerCardRenderer:
    """Renders the individual player HUD cards."""

    def __init__(
        self,
        font_small: pygame.font.Font,
        panel_drawer: Callable[[pygame.Surface, pygame.Rect, tuple, tuple, int, int, bool], None],
    ):
        self._font_small = font_small
        self._font_wins = pygame.font.SysFont("consolas", 36, bold=True)
        self._draw_panel = panel_drawer
        self._orb_icon_cache: dict[tuple[str, int], pygame.Surface] = {}
        self._portrait_cache: dict[tuple[str, int], pygame.Surface] = {}

    def draw(
        self,
        surface: pygame.Surface,
        players: List,
        round_wins: Optional[List[int]] = None,
        target_score: int = 1,
    ) -> None:
        if not players:
            return
        render_players = list(players)
        rounds = round_wins if isinstance(round_wins, list) else []
        card_w, card_h = CARD_WIDTH, CARD_HEIGHT
        rects = self._player_card_rects(len(render_players), card_w, card_h)
        for idx, player in enumerate(render_players):
            if idx >= len(rects):
                break
            border_color = CARD_COLOR_PALETTE[idx % len(CARD_COLOR_PALETTE)]
            wins = int(max(0, rounds[idx])) if idx < len(rounds) else 0
            self._draw_player_card(surface, rects[idx], player, idx, border_color)
            eliminated = bool(getattr(player, "_eliminated", False))
            self._draw_wins_footer(surface, rects[idx], wins, border_color, eliminated)

    def _player_card_rects(self, count: int, width: int, height: int) -> List[pygame.Rect]:
        rects: List[pygame.Rect] = []
        if count <= 0:
            return rects

        if count == 1:
            rects.append(pygame.Rect((WINDOW_SIZE[0] - width) // 2, CARD_MARGIN_Y, width, height))
            return rects

        columns = 2
        x_positions = [CARD_MARGIN_X, WINDOW_SIZE[0] - width - CARD_MARGIN_X]
        rows = math.ceil(count / columns)
        for row in range(rows):
            y = CARD_MARGIN_Y + row * (height + CARD_ROW_GAP)
            for col in range(columns):
                idx = row * columns + col
                if idx >= count:
                    break
                x = x_positions[col]
                rects.append(pygame.Rect(x, y, width, height))
        return rects

    def _draw_player_card(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        player,
        index: int,
        border_color: tuple,
    ) -> None:
        if player is None:
            return
        eliminated = bool(getattr(player, "_eliminated", False))
        if eliminated:
            border_color = (120, 120, 135)

        self._draw_panel(surface, rect, HUD_PANEL_BG, border_color,
                         HUD_PANEL_BORDER_WIDTH, HUD_PANEL_RADIUS, glow=True)

        charges = getattr(player, "power_orb_charges", 0)
        orb_label = None
        orb_timer = 0.0
        orb_infinite = False
        orb_duration = 0.0
        if hasattr(player, "get_active_orb_status"):
            status = player.get_active_orb_status()
            if status:
                orb_label, orb_timer, orb_infinite, orb_duration = status
        orb_color = self._orb_color_for_label(orb_label)

        accent_rect = pygame.Rect(rect.left + 10, rect.top + 10, rect.width - 20, 6)
        self._draw_orb_timer_line(surface, accent_rect, orb_color if orb_label else border_color, orb_label,
                                  orb_timer, orb_infinite, orb_duration)

        portrait = self._headshot_surface(player, 68, border_color)
        portrait_rect = portrait.get_rect()
        portrait_rect.topleft = (rect.left + 14, rect.top + 16)
        surface.blit(portrait, portrait_rect)

        if orb_label:
            orb_icon_center = (portrait_rect.centerx, portrait_rect.bottom + 25)
            self._draw_orb_icon(surface, orb_icon_center, orb_label, True, size=40)

        text_x = portrait_rect.right + 12
        text_y = rect.top + 14
        label = self._font_small.render(f"P{index + 1}", True, border_color)
        label_bg = pygame.Rect(text_x - 2, text_y - 2, label.get_width() + 10, label.get_height() + 6)
        self._draw_badge(surface, label_bg, CARD_STATUS_BG, border_color, f"P{index + 1}", border_color)
        name = getattr(player, "character_name", "Unknown")
        name_surf = self._font_small.render(name.upper(), True, (255, 255, 255))
        surface.blit(name_surf, (label_bg.right + 8, text_y))

        if getattr(player, "is_ai", False):
            ai_text = "AI"
            ai_rect = pygame.Rect(rect.right - 48, rect.top + 14, 34, 18)
            self._draw_badge(surface, ai_rect, (34, 52, 84, 230), (110, 150, 210), ai_text, (235, 245, 255))

        power = getattr(player, "power", None)
        power_name = getattr(power, "NAME", None) or "NONE"
        power_color = getattr(power, "COLOR", border_color)
        power_chip_text = f"POWER: {power_name.upper()}"
        power_chip_rect = pygame.Rect(text_x, rect.top + 42, rect.width - (text_x - rect.left) - 16, 22)
        self._draw_badge(surface, power_chip_rect, (*power_color[:3], 55), power_color, power_chip_text, (255, 255, 255))

        lives = self._player_lives_count(player)
        lives_label = self._font_small.render("LIVES", True, border_color)
        surface.blit(lives_label, (text_x, rect.top + 68))
        lives_rect = pygame.Rect(text_x, rect.top + 86, rect.width - (text_x - rect.left) - 16, 28)
        self._draw_lives_badge(surface, lives_rect, lives, border_color)
        
        self._draw_health_bar(surface, rect, player, border_color)
        
        ammo = getattr(player, "_projectile_ammo", 5)
        ammo_label = self._font_small.render("AMMO", True, border_color)
        surface.blit(ammo_label, (text_x, rect.top + 155))
        ammo_rect = pygame.Rect(text_x, rect.top + 173, rect.width - (text_x - rect.left) - 16, 20)
        self._draw_ammo_bar(surface, ammo_rect, ammo, getattr(player, "_max_projectile_ammo", 5), border_color)
        
        ult_charges = getattr(player, "_ultimate_charges", 0)
        ult_label = self._font_small.render("ULT", True, border_color)
        surface.blit(ult_label, (text_x, rect.top + 200))
        ult_rect = pygame.Rect(text_x, rect.top + 218, 50, 20)
        self._draw_badge(surface, ult_rect, (255, 100, 20, 100) if ult_charges > 0 else CARD_STATUS_BG, 
                        (255, 140, 50) if ult_charges > 0 else CARD_STATUS_BORDER, 
                        str(ult_charges), (255, 255, 255))

        status_text = self._status_summary(player, orb_label, orb_timer, orb_infinite, orb_duration, charges)
        status_label = self._font_small.render("STATUS", True, border_color)
        surface.blit(status_label, (text_x, rect.top + 120))
        status_rect = pygame.Rect(text_x, rect.top + 138, rect.width - (text_x - rect.left) - 16, 18)
        self._draw_badge(surface, status_rect, CARD_STATUS_BG, orb_color if orb_label else CARD_STATUS_BORDER, status_text, CARD_TEXT_DIM)

        if eliminated:
            self._draw_eliminated_overlay(surface, rect)

    def _draw_wins_footer(
        self,
        surface: pygame.Surface,
        card_rect: pygame.Rect,
        round_wins: int,
        border_color: tuple,
        eliminated: bool,
    ) -> None:
        """Draw a large wins number under each player card."""
        wins_text = str(max(0, int(round_wins)))
        wins_surf = self._font_wins.render(wins_text, True, (250, 252, 255))

        footer_w = max(74, wins_surf.get_width() + 30)
        footer_h = max(38, wins_surf.get_height() + 8)
        footer_rect = pygame.Rect(0, 0, footer_w, footer_h)
        footer_rect.centerx = card_rect.centerx
        footer_rect.top = card_rect.bottom + 8

        win_border = (130, 130, 145) if eliminated else border_color
        badge = pygame.Surface(footer_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(badge, CARD_WINS_BG, badge.get_rect(), border_radius=12)
        surface.blit(badge, footer_rect.topleft)
        pygame.draw.rect(surface, win_border, footer_rect, 2, border_radius=12)

        wins_rect = wins_surf.get_rect(center=footer_rect.center)
        surface.blit(wins_surf, wins_rect)

    def _draw_eliminated_overlay(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        overlay.fill((8, 10, 16, 150))
        pygame.draw.line(overlay, (255, 90, 90, 220), (12, 12), (rect.width - 12, rect.height - 12), 7)
        pygame.draw.line(overlay, (255, 90, 90, 220), (rect.width - 12, 12), (12, rect.height - 12), 7)
        surface.blit(overlay, rect.topleft)

        badge_rect = pygame.Rect(rect.left + 16, rect.centery - 14, rect.width - 32, 28)
        self._draw_badge(surface, badge_rect, (30, 18, 22, 230), (255, 90, 90), "ELIMINATED", (255, 225, 225))

    def _draw_badge(self, surface: pygame.Surface, rect: pygame.Rect,
                    fill_color: tuple, border_color: tuple, text: str, text_color: tuple) -> None:
        badge = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(badge, fill_color, badge.get_rect(), border_radius=max(8, rect.height // 2))
        surface.blit(badge, rect.topleft)
        pygame.draw.rect(surface, border_color, rect, 1, border_radius=max(8, rect.height // 2))
        text_surf = self._font_small.render(text, True, text_color)
        text_rect = text_surf.get_rect(center=rect.center)
        surface.blit(text_surf, text_rect)

    def _headshot_surface(self, player, size: int, border_color: tuple) -> pygame.Surface:
        portrait = pygame.Surface((size, size), pygame.SRCALPHA)
        base = self._portrait_image(player, size)
        if base is None:
            base = self._placeholder_portrait(size, border_color)
        portrait.blit(base, (0, 0))
        mask = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (size // 2, size // 2), size // 2)
        portrait.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        pygame.draw.circle(portrait, border_color, (size // 2, size // 2), size // 2, 2)
        return portrait

    def _draw_power_icon(self, surface: pygame.Surface, center: tuple[int, int], color: tuple) -> None:
        icon = self._orb_icon_surface("power", 34)
        if icon:
            tinted = icon.copy()
            tint = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
            tint.fill((color[0], color[1], color[2], 140))
            tinted.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(tinted, tinted.get_rect(center=center))
            return
        radius = 14
        fallback = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(fallback, color, (radius, radius), radius)
        pygame.draw.circle(fallback, (255, 255, 255, 140), (radius, radius), radius, 2)
        surface.blit(fallback, fallback.get_rect(center=center))

    def _draw_lives_badge(self, surface: pygame.Surface, rect: pygame.Rect, lives: int, border_color: tuple) -> None:
        badge = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(badge, CARD_STATUS_BG, badge.get_rect(), border_radius=max(8, rect.height // 2))
        surface.blit(badge, rect.topleft)
        pygame.draw.rect(surface, border_color, rect, 1, border_radius=max(8, rect.height // 2))

        life_icon = self._orb_icon_surface("life", 22)
        icon_left = rect.left + 10
        if life_icon:
            icon_rect = life_icon.get_rect(midleft=(icon_left, rect.centery))
            surface.blit(life_icon, icon_rect)
            count_x = icon_rect.right + 8
        else:
            fallback_radius = 7
            pygame.draw.circle(surface, (255, 105, 180), (icon_left + fallback_radius, rect.centery), fallback_radius)
            count_x = icon_left + fallback_radius * 2 + 8

        count_surf = self._font_small.render(str(max(0, lives)), True, (255, 255, 255))
        count_rect = count_surf.get_rect(midleft=(count_x, rect.centery))
        surface.blit(count_surf, count_rect)

    def _draw_charge_pips(self, surface: pygame.Surface, origin: tuple[int, int],
                          charges: int, accent_color: tuple) -> None:
        required = max(1, POWER_ORBS_REQUIRED)
        icon_template = self._orb_icon_surface("power", 26)
        start_x = origin[0]
        y = origin[1]
        spacing = icon_template.get_width() + 8 if icon_template else 18
        for idx in range(required):
            cx = start_x + idx * spacing
            filled = idx < charges
            if icon_template:
                icon = icon_template.copy()
                if not filled:
                    icon.fill((90, 90, 120, 200), special_flags=pygame.BLEND_RGBA_MULT)
                rect = icon.get_rect(center=(cx, y))
                surface.blit(icon, rect)
            else:
                radius = 6
                color = accent_color if filled else (80, 80, 90)
                pygame.draw.circle(surface, color, (cx, y), radius)
                pygame.draw.circle(surface, (255, 255, 255, 60), (cx, y), radius, 1)

    def _draw_orb_icon(self, surface: pygame.Surface, center: tuple[int, int],
                       label: Optional[str], active: bool, size: int = 40) -> None:
        key = self._orb_key_from_label(label)
        icon = self._orb_icon_surface(key, size)
        if icon:
            to_blit = icon.copy()
            if not active:
                to_blit.fill((90, 90, 120, 200), special_flags=pygame.BLEND_RGBA_MULT)
            rect = to_blit.get_rect(center=center)
            surface.blit(to_blit, rect)
            return
        color = self._orb_color_for_label(label)
        radius = 14
        orb = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        fill_color = color if active else (55, 55, 70)
        pygame.draw.circle(orb, fill_color, (radius, radius), radius)
        pygame.draw.circle(orb, (255, 255, 255, 90), (radius - 4, radius - 6), radius // 2)
        pygame.draw.circle(orb, (255, 255, 255, 140), (radius, radius), radius, 2)
        surface.blit(orb, orb.get_rect(center=center))

    def _draw_orb_timer_line(self, surface: pygame.Surface, rect: pygame.Rect,
                              color: tuple, label: Optional[str], timer: float,
                              indefinite: bool, duration: float) -> None:
        line_rect = rect.copy()
        if line_rect.width <= 0 or line_rect.height <= 0:
            return

        line_color = color or CARD_TIMER_FILL
        pygame.draw.rect(surface, CARD_TIMER_BORDER, line_rect, border_radius=max(2, line_rect.height // 2))
        inner = line_rect.inflate(-2, -2)
        pygame.draw.rect(surface, CARD_TIMER_BG, inner, border_radius=max(1, inner.height // 2))

        if not label:
            return

        if indefinite or duration <= 0:
            fill_width = inner.width
        else:
            if timer <= 0:
                return
            progress = max(0.0, min(1.0, timer / duration))
            fill_width = max(2, int(inner.width * progress))

        fill_rect = pygame.Rect(inner.left, inner.top, fill_width, inner.height)
        pygame.draw.rect(surface, line_color, fill_rect, border_radius=max(1, inner.height // 2))

    def _orb_color_for_label(self, label: Optional[str]) -> tuple:
        if not label:
            return (110, 110, 130)
        return ORB_ICON_COLORS.get(label.lower(), CARD_TIMER_FILL)

    def _status_summary(self, player, orb_label: Optional[str], orb_timer: float,
                        orb_infinite: bool, orb_duration: float, charges: int) -> str:
        if orb_label:
            return orb_label.upper()
        if charges > 0 and getattr(player, "power", None):
            return "POWER READY"
        return "READY"

    def _player_lives_count(self, player) -> int:
        if getattr(player, "_eliminated", False):
            return 0
        extra_lives = int(getattr(player, "_extra_lives", 0))
        return extra_lives

    def _draw_ammo_bar(self, surface: pygame.Surface, rect: pygame.Rect, ammo: int, max_ammo: int, border_color: tuple) -> None:
        """Draw ammo bar for projectiles."""
        bg_rect = pygame.Rect(rect.left, rect.top, rect.width, rect.height)
        pygame.draw.rect(surface, (40, 40, 50), bg_rect, border_radius=4)
        
        if max_ammo > 0:
            ammo_ratio = ammo / max_ammo
            ammo_width = int(rect.width * ammo_ratio)
            if ammo_width > 0:
                ammo_rect = pygame.Rect(rect.left, rect.top, ammo_width, rect.height)
                if ammo_ratio > 0.6:
                    ammo_color = (100, 150, 200)
                elif ammo_ratio > 0.2:
                    ammo_color = (200, 180, 80)
                else:
                    ammo_color = (150, 80, 80)
                pygame.draw.rect(surface, ammo_color, ammo_rect, border_radius=4)
        
        pygame.draw.rect(surface, border_color, bg_rect, 1, border_radius=4)
        
        ammo_text = f"{ammo}/{max_ammo}"
        text_surf = self._font_small.render(ammo_text, True, (255, 255, 255))
        text_rect = text_surf.get_rect(center=(rect.left + rect.width // 2, rect.top + rect.height // 2))
        surface.blit(text_surf, text_rect)

    def _draw_health_bar(self, surface: pygame.Surface, rect: pygame.Rect, player, border_color: tuple) -> None:
        """Draw a health bar for the player."""
        health = int(getattr(player, "_health", 3))
        max_health = int(getattr(player, "_max_health", 3))
        
        if max_health <= 0:
            return
        
        bar_width = rect.width
        bar_height = 16
        bar_x = rect.left
        bar_y = rect.top + 115
        
        bg_rect = pygame.Rect(bar_x, bar_y, bar_width, bar_height)
        pygame.draw.rect(surface, (40, 40, 50), bg_rect, border_radius=4)
        
        health_ratio = health / max_health
        health_width = int(bar_width * health_ratio)
        if health_width > 0:
            health_rect = pygame.Rect(bar_x, bar_y, health_width, bar_height)
            
            if health_ratio > 0.6:
                health_color = (60, 200, 80)
            elif health_ratio > 0.3:
                health_color = (220, 200, 50)
            else:
                health_color = (200, 60, 60)
            
            pygame.draw.rect(surface, health_color, health_rect, border_radius=4)
        
        pygame.draw.rect(surface, border_color, bg_rect, 2, border_radius=4)
        
        hp_text = f"{health}/{max_health}"
        text_surf = self._font_small.render(hp_text, True, (255, 255, 255))
        text_rect = text_surf.get_rect(center=(bar_x + bar_width // 2, bar_y + bar_height // 2))
        surface.blit(text_surf, text_rect)

    def _orb_key_from_label(self, label: Optional[str]) -> Optional[str]:
        if not label:
            return None
        return ORB_LABEL_TO_KEY.get(label.lower())

    def _orb_icon_surface(self, key: Optional[str], size: int) -> pygame.Surface | None:
        if not key:
            return None
        cache_key = (key, size)
        cached = self._orb_icon_cache.get(cache_key)
        if cached is not None:
            return cached
        path = ORB_ICON_PATHS.get(key)
        if not path:
            return None
        try:
            image = pygame.image.load(path).convert_alpha()
        except Exception:
            return None
        scaled = pygame.transform.smoothscale(image, (size, size))
        self._orb_icon_cache[cache_key] = scaled
        return scaled

    def _portrait_image(self, player, size: int) -> pygame.Surface | None:
        name = getattr(player, "character_name", "").strip()
        if not name:
            return None
        key = (name.lower(), size)
        cached = self._portrait_cache.get(key)
        if cached is not None:
            return cached.copy()
        path = self._resolve_portrait_path(name)
        if path is None:
            return None
        try:
            image = pygame.image.load(path.as_posix()).convert_alpha()
        except Exception:
            return None
        square = self._scale_square_surface(image, size)
        self._portrait_cache[key] = square
        return square.copy()

    def _resolve_portrait_path(self, name: str):
        base = name.strip()
        directories = self._portrait_dirs()
        if not directories:
            return None
        variants = [
            base,
            base.replace(" ", "_"),
            base.replace(" ", ""),
            base.lower().replace(" ", ""),
            base.lower().replace(" ", "_"),
        ]
        seen = set()
        for directory in directories:
            for variant in variants:
                variant = variant.strip()
                if not variant:
                    continue
                candidate = directory / f"{variant}.png"
                if candidate in seen:
                    continue
                seen.add(candidate)
                if candidate.exists():
                    return candidate
        return None

    def _portrait_dirs(self) -> List[Path]:
        dirs: List[Path] = []
        primary = PLAYER_PORTRAIT_DIR
        typo = primary.parent / "portait"
        for directory in [primary, typo]:
            if directory is None:
                continue
            try:
                exists = directory.exists()
            except Exception:
                exists = False
            if exists and directory not in dirs:
                dirs.append(directory)
        return dirs

    def _scale_square_surface(self, image: pygame.Surface, size: int) -> pygame.Surface:
        width, height = image.get_width(), image.get_height()
        crop_side = min(width, height)
        offset_x = max(0, (width - crop_side) // 2)
        offset_y = max(0, int((height - crop_side) * 0.2))
        if offset_y + crop_side > height:
            offset_y = max(0, height - crop_side)
        crop_rect = pygame.Rect(offset_x, offset_y, crop_side, crop_side)
        cropped = image.subsurface(crop_rect).copy()
        return pygame.transform.smoothscale(cropped, (size, size))

    def _placeholder_portrait(self, size: int, border_color: tuple) -> pygame.Surface:
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        pygame.draw.circle(surf, (60, 60, 90), center, size // 2)
        pygame.draw.circle(surf, (255, 255, 255, 40), center, size // 2, 2)
        pygame.draw.circle(surf, border_color, center, size // 2 - 4, 1)
        return surf
