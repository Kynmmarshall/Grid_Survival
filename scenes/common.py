from __future__ import annotations

import pygame

from audio import get_audio
from settings import AUDIO_VOLUME_STEP, FONT_PATH_SMALL, FONT_SIZE_SMALL


def _load_font(path: str, size: int, bold: bool = False) -> pygame.font.Font:
    """Try to load a TTF font; fall back to Consolas system font."""
    try:
        return pygame.font.Font(path, size)
    except (pygame.error, FileNotFoundError, OSError):
        try:
            return pygame.font.SysFont("consolas", size, bold=bold)
        except Exception:
            return pygame.font.Font(None, size)


def _draw_rounded_rect(surface: pygame.Surface, rect: pygame.Rect,
                       color: tuple, border_color: tuple,
                       border_width: int = 2, radius: int = 12) -> None:
    """Render a rounded rectangle with optional border."""
    bg = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(bg, color, bg.get_rect(), border_radius=radius)
    surface.blit(bg, rect.topleft)
    pygame.draw.rect(surface, border_color, rect, border_width, border_radius=radius)


class SceneAudioOverlay:
    """Small reusable audio settings widget for non-game screens."""

    def __init__(self):
        self.audio = get_audio()
        self._font = _load_font(FONT_PATH_SMALL, max(14, FONT_SIZE_SMALL - 2))
        self._font_hint = _load_font(FONT_PATH_SMALL, 12)

        self.mute_rect = pygame.Rect(20, 20, 120, 38)
        self.volume_rect = pygame.Rect(20, 64, 190, 52)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle shared volume controls. Returns True when input is consumed."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.mute_rect.collidepoint(event.pos):
                self.audio.toggle_mute()
                return True

        if event.type == pygame.MOUSEWHEEL:
            if event.y:
                self.audio.adjust_volume(event.y * AUDIO_VOLUME_STEP)
                return True

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_PAGEUP, pygame.K_EQUALS, pygame.K_KP_PLUS, pygame.K_RIGHTBRACKET):
                self.audio.adjust_volume(AUDIO_VOLUME_STEP)
                return True
            if event.key in (pygame.K_PAGEDOWN, pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_LEFTBRACKET):
                self.audio.adjust_volume(-AUDIO_VOLUME_STEP)
                return True

        return False

    def draw(self, surface: pygame.Surface) -> None:
        """Render mute toggle + volume meter + compact control hint."""
        is_muted = self.audio.is_muted
        volume = max(0.0, min(1.0, self.audio.get_volume()))

        mute_border = (220, 90, 90) if is_muted else (80, 210, 125)
        mute_bg = (18, 24, 36, 215)
        _draw_rounded_rect(surface, self.mute_rect, mute_bg, mute_border, 2, 10)

        mute_text = "MUTED" if is_muted else "AUDIO"
        mute_surf = self._font.render(mute_text, True, (240, 240, 245))
        surface.blit(mute_surf, mute_surf.get_rect(center=self.mute_rect.center))

        vol_active = (not is_muted) and volume > 0.0
        vol_border = (80, 210, 125) if vol_active else (220, 90, 90)
        _draw_rounded_rect(surface, self.volume_rect, mute_bg, vol_border, 2, 10)

        vol_label = self._font.render("VOL", True, vol_border)
        vol_value = "MUTED" if is_muted else f"{int(round(volume * 100)):02d}%"
        vol_value_surf = self._font.render(vol_value, True, (240, 240, 245))

        surface.blit(vol_label, (self.volume_rect.left + 10, self.volume_rect.top + 8))
        surface.blit(vol_value_surf, vol_value_surf.get_rect(top=self.volume_rect.top + 8, right=self.volume_rect.right - 10))

        bar = pygame.Rect(self.volume_rect.left + 10, self.volume_rect.bottom - 14, self.volume_rect.width - 20, 8)
        pygame.draw.rect(surface, vol_border, bar, 1, border_radius=4)
        inner = bar.inflate(-2, -2)
        pygame.draw.rect(surface, (10, 14, 22), inner, border_radius=3)
        fill_w = int(inner.width * volume) if vol_active else 0
        if fill_w > 0:
            fill = pygame.Rect(inner.left, inner.top, fill_w, inner.height)
            pygame.draw.rect(surface, vol_border, fill, border_radius=3)

        hint_rect = pygame.Rect(self.volume_rect.left, self.volume_rect.bottom + 6, self.volume_rect.width, 22)
        hint_bg = pygame.Surface(hint_rect.size, pygame.SRCALPHA)
        hint_bg.fill((8, 12, 18, 165))
        surface.blit(hint_bg, hint_rect.topleft)
        hint = self._font_hint.render("VOL: +/- OR [ ] OR WHEEL", True, (180, 190, 210))
        surface.blit(hint, hint.get_rect(center=hint_rect.center))


__all__ = ["_load_font", "_draw_rounded_rect", "SceneAudioOverlay"]
