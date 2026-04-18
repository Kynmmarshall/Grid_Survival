from __future__ import annotations

import threading
from typing import Any, Iterable

import pygame

from audio import get_audio
from settings import AUDIO_VOLUME_STEP, FONT_PATH_SMALL, FONT_SIZE_SMALL, TARGET_FPS


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


_STATUS_SERVICE: Any | None = None
_STATUS_LOCK = threading.Lock()
_STATUS_ONLINE: bool | None = None
_STATUS_PENDING: bool | None = None
_STATUS_CHECK_RUNNING = False
_STATUS_CHECK_TIMER = 999.0
_STATUS_CHECK_INTERVAL = 3.5


def set_online_status_service(service: Any | None) -> None:
    """Register account service used to probe online/offline state."""
    global _STATUS_SERVICE, _STATUS_ONLINE, _STATUS_PENDING, _STATUS_CHECK_RUNNING, _STATUS_CHECK_TIMER
    with _STATUS_LOCK:
        _STATUS_SERVICE = service
        _STATUS_ONLINE = None
        _STATUS_PENDING = None
        _STATUS_CHECK_RUNNING = False
        _STATUS_CHECK_TIMER = _STATUS_CHECK_INTERVAL


def set_online_status_hint(is_online: bool | None) -> None:
    """Allow callers with fresh connectivity checks to push immediate status."""
    global _STATUS_ONLINE
    with _STATUS_LOCK:
        _STATUS_ONLINE = None if is_online is None else bool(is_online)


def _start_online_status_probe() -> None:
    global _STATUS_CHECK_RUNNING
    with _STATUS_LOCK:
        if _STATUS_CHECK_RUNNING:
            return
        service = _STATUS_SERVICE
        _STATUS_CHECK_RUNNING = True

    if service is None:
        with _STATUS_LOCK:
            _STATUS_CHECK_RUNNING = False
            _STATUS_ONLINE = None
        return

    def _worker() -> None:
        status = False
        try:
            status = bool(service.is_remote_online())
        except Exception:
            status = False

        with _STATUS_LOCK:
            global _STATUS_PENDING, _STATUS_CHECK_RUNNING
            _STATUS_PENDING = status
            _STATUS_CHECK_RUNNING = False

    threading.Thread(target=_worker, daemon=True).start()


def update_online_status(dt: float = 0.0, force: bool = False) -> None:
    """Update global online status timer and schedule probe when needed."""
    global _STATUS_CHECK_TIMER, _STATUS_ONLINE, _STATUS_PENDING

    should_probe = False
    with _STATUS_LOCK:
        _STATUS_CHECK_TIMER += max(0.0, float(dt))

        if _STATUS_PENDING is not None:
            _STATUS_ONLINE = bool(_STATUS_PENDING)
            _STATUS_PENDING = None

        if force or (_STATUS_CHECK_TIMER >= _STATUS_CHECK_INTERVAL):
            if not _STATUS_CHECK_RUNNING:
                _STATUS_CHECK_TIMER = 0.0
                should_probe = True

    if should_probe:
        _start_online_status_probe()


def _online_status_snapshot() -> tuple[bool | None, bool]:
    with _STATUS_LOCK:
        return _STATUS_ONLINE, _STATUS_CHECK_RUNNING


def draw_online_status_badge(
    surface: pygame.Surface,
    reserved_rects: Iterable[pygame.Rect] | None = None,
    *,
    margin: int = 14,
    preferred_corners: tuple[str, ...] = ("top-right", "top-left", "bottom-right", "bottom-left"),
) -> None:
    """Draw a compact online/offline badge while avoiding reserved UI regions."""
    update_online_status(1.0 / max(1, TARGET_FPS))
    online, checking = _online_status_snapshot()

    if online is None:
        label = "CHECKING"
        bg = (74, 74, 54, 220)
        border = (222, 198, 124)
        dot = (248, 218, 132)
    elif online:
        label = "ONLINE"
        bg = (34, 78, 52, 220)
        border = (128, 224, 174)
        dot = (130, 244, 178)
    else:
        label = "OFFLINE"
        bg = (86, 42, 42, 220)
        border = (236, 154, 154)
        dot = (255, 168, 168)

    if checking and online is not None:
        label += " *"

    font = _load_font(FONT_PATH_SMALL, max(13, FONT_SIZE_SMALL - 3), bold=True)
    text = font.render(label, True, (244, 248, 255))
    badge_w = max(132, text.get_width() + 44)
    badge_h = max(30, text.get_height() + 12)

    sw, sh = surface.get_size()
    candidates = {
        "top-left": pygame.Rect(margin, margin, badge_w, badge_h),
        "top-right": pygame.Rect(sw - margin - badge_w, margin, badge_w, badge_h),
        "bottom-left": pygame.Rect(margin, sh - margin - badge_h, badge_w, badge_h),
        "bottom-right": pygame.Rect(sw - margin - badge_w, sh - margin - badge_h, badge_w, badge_h),
    }

    blocked = [r for r in (reserved_rects or []) if isinstance(r, pygame.Rect)]

    def _overlap_area(rect: pygame.Rect) -> int:
        area = 0
        for other in blocked:
            clip = rect.clip(other)
            if clip.width > 0 and clip.height > 0:
                area += clip.width * clip.height
        return area

    chosen_rect: pygame.Rect | None = None
    best_area: int | None = None
    for key in preferred_corners:
        rect = candidates.get(key)
        if rect is None:
            continue
        area = _overlap_area(rect)
        if area == 0:
            chosen_rect = rect
            break
        if best_area is None or area < best_area:
            best_area = area
            chosen_rect = rect

    if chosen_rect is None:
        chosen_rect = candidates["top-right"]

    _draw_rounded_rect(surface, chosen_rect, bg, border, 2, 10)
    pygame.draw.circle(surface, dot, (chosen_rect.left + 14, chosen_rect.centery), 5)
    surface.blit(text, text.get_rect(midleft=(chosen_rect.left + 26, chosen_rect.centery)))


class SceneAudioOverlay:
    """Small reusable audio settings widget for non-game screens."""

    def __init__(self, show_online_status: bool = True):
        self.audio = get_audio()
        self._font = _load_font(FONT_PATH_SMALL, max(14, FONT_SIZE_SMALL - 2))
        self._font_hint = _load_font(FONT_PATH_SMALL, 12)
        self._show_online_status = bool(show_online_status)

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

        if self._show_online_status:
            draw_online_status_badge(
                surface,
                reserved_rects=(self.mute_rect, self.volume_rect, hint_rect),
                preferred_corners=("top-right", "bottom-right", "top-left", "bottom-left"),
            )


__all__ = [
    "_load_font",
    "_draw_rounded_rect",
    "SceneAudioOverlay",
    "set_online_status_service",
    "set_online_status_hint",
    "update_online_status",
    "draw_online_status_badge",
]
