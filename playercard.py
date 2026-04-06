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
    "power charge": (200, 80, 255),
    "bomb detonation": (255, 90, 70),
}
ORB_LABEL_TO_KEY = {
    "speed boost": "speed",
    "shield": "shield",
    "frozen": "freeze",
    "power charge": "power",
    "bomb detonation": "bomb",
}

CARD_WIDTH = 282
CARD_HEIGHT = 152
CARD_MARGIN_X = 20
CARD_MARGIN_Y = 18
CARD_ROW_GAP = 16
CARD_STATUS_BG = (18, 22, 34, 220)
CARD_STATUS_BORDER = (92, 112, 150)
CARD_TEXT_DIM = (190, 200, 215)
CARD_TEXT_FAINT = (145, 155, 175)


class PlayerCardRenderer:
    """Renders the individual player HUD cards."""

    def __init__(
        self,
        font_small: pygame.font.Font,
        panel_drawer: Callable[[pygame.Surface, pygame.Rect, tuple, tuple, int, int, bool], None],
    ):
        self._font_small = font_small
        self._draw_panel = panel_drawer
        self._orb_icon_cache: dict[tuple[str, int], pygame.Surface] = {}
        self._portrait_cache: dict[tuple[str, int], pygame.Surface] = {}

    def draw(self, surface: pygame.Surface, players: List) -> None:
        if not players:
            return
        render_players = self._active_players(players)
        card_w, card_h = CARD_WIDTH, CARD_HEIGHT
        rects = self._player_card_rects(len(render_players), card_w, card_h)
        for idx, player in enumerate(render_players):
            if idx >= len(rects):
                break
            border_color = CARD_COLOR_PALETTE[idx % len(CARD_COLOR_PALETTE)]
            self._draw_player_card(surface, rects[idx], player, idx, border_color)

    def _active_players(self, players: List) -> List:
        active = [p for p in players if not getattr(p, "_eliminated", False)]
        return active or players

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

    def _draw_player_card(self, surface: pygame.Surface, rect: pygame.Rect, player, index: int, border_color: tuple) -> None:
        if player is None:
            return
        self._draw_panel(surface, rect, HUD_PANEL_BG, border_color,
                         HUD_PANEL_BORDER_WIDTH, HUD_PANEL_RADIUS, glow=True)

        accent_rect = pygame.Rect(rect.left + 10, rect.top + 10, rect.width - 20, 5)
        pygame.draw.rect(surface, (*border_color[:3], 180), accent_rect, border_radius=3)

        portrait = self._headshot_surface(player, 68, border_color)
        portrait_rect = portrait.get_rect()
        portrait_rect.topleft = (rect.left + 14, rect.top + 16)
        surface.blit(portrait, portrait_rect)

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
        power_name = getattr(power, "NAME", "No Power")
        power_color = getattr(power, "COLOR", border_color)
        power_chip_text = f"{power_name.upper()}"
        power_chip_rect = pygame.Rect(text_x, rect.top + 42, rect.width - (text_x - rect.left) - 16, 22)
        self._draw_badge(surface, power_chip_rect, (*power_color[:3], 55), power_color, power_chip_text, (255, 255, 255))

        icon_row_y = rect.top + 74
        self._draw_power_icon(surface, (text_x + 22, icon_row_y), power_color)

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
        self._draw_orb_icon(surface, (text_x + 74, icon_row_y), orb_label, bool(orb_label))
        self._draw_charge_pips(surface, (text_x + 128, icon_row_y), charges, border_color)

        status_text = self._status_summary(player, orb_label, orb_timer, orb_infinite, orb_duration, charges)
        status_surf = self._font_small.render(status_text, True, CARD_TEXT_DIM)
        surface.blit(status_surf, (text_x, rect.top + 98))

        controls_text = self._controls_summary(player)
        controls_rect = pygame.Rect(rect.left + 14, rect.bottom - 34, rect.width - 28, 18)
        self._draw_badge(surface, controls_rect, CARD_STATUS_BG, CARD_STATUS_BORDER, controls_text, CARD_TEXT_FAINT)

        self._draw_orb_timer_line(surface, rect, orb_color, orb_label,
                                  orb_timer, orb_infinite, orb_duration)

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

<<<<<<< Updated upstream
=======
    def _draw_lives_badge(self, surface: pygame.Surface, rect: pygame.Rect, lives: int, border_color: tuple) -> None:
        badge = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(badge, CARD_STATUS_BG, badge.get_rect(), border_radius=max(8, rect.height // 2))
        surface.blit(badge, rect.topleft)
        pygame.draw.rect(surface, border_color, rect, 1, border_radius=max(8, rect.height // 2))

        life_icon = self._orb_icon_surface("life", 16)
        if life_icon:
            for i in range(max(0, lives)):
                icon_x = rect.left + 10 + i * 18
                if icon_x + 16 < rect.right:
                    icon_rect = life_icon.get_rect(midleft=(icon_x, rect.centery))
                    surface.blit(life_icon, icon_rect)
        else:
            fallback_radius = 6
            for i in range(max(0, lives)):
                icon_x = rect.left + 10 + i * 18
                if icon_x + fallback_radius * 2 < rect.right:
                    pygame.draw.circle(surface, (255, 105, 180), (icon_x + fallback_radius, rect.centery), fallback_radius)

>>>>>>> Stashed changes
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
                       label: Optional[str], active: bool) -> None:
        key = self._orb_key_from_label(label)
        icon = self._orb_icon_surface(key, 40)
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

    def _orb_color_for_label(self, label: Optional[str]) -> tuple:
        if not label:
            return (110, 110, 130)
        return ORB_ICON_COLORS.get(label.lower(), CARD_TIMER_FILL)

    def _status_summary(self, player, orb_label: Optional[str], orb_timer: float,
                        orb_infinite: bool, orb_duration: float, charges: int) -> str:
        if orb_label:
            if orb_infinite or orb_duration <= 0:
                return orb_label.upper()
            return f"{orb_label.upper()} {orb_timer:.1f}s"
        if charges > 0:
            return f"POWER ORBS {charges}/{POWER_ORBS_REQUIRED}"
        if getattr(player, "is_ai", False):
            return "AI CONTROLLED"
        return "READY"

    def _controls_summary(self, player) -> str:
        controls = getattr(player, "controls", {}) or {}
        move = self._movement_label(controls)
        jump = self._key_label(controls.get("jump"), "SPACE")
        power = self._key_label(controls.get("power"), "POWER")
        return f"MOVE {move}  •  JUMP {jump}  •  POWER {power}"

    def _movement_label(self, controls: dict) -> str:
        key_names = [self._key_label(controls.get(action), "") for action in ("left", "right", "up", "down")]
        key_set = {name for name in key_names if name}
        if key_set == {"W", "A", "S", "D"}:
            return "WASD"
        if key_set == {"LEFT", "RIGHT", "UP", "DOWN"}:
            return "ARROWS"
        if not key_set:
            return "MOVE"
        return "/".join(sorted(key_set))

    def _key_label(self, key_code: Optional[int], fallback: str) -> str:
        if key_code is None:
            return fallback
        name = pygame.key.name(key_code).upper()
        if name in {"LEFT SHIFT", "RIGHT SHIFT"}:
            return "SHIFT"
        if name in {"LEFT CTRL", "RIGHT CTRL"}:
            return "CTRL"
        if name == "SLASH":
            return "/"
        if name == "BACKSLASH":
            return "\\"
        if name == "SPACE":
            return "SPACE"
        return name.replace("LEFT ", "").replace("RIGHT ", "").strip()

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
