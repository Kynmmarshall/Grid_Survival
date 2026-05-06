from __future__ import annotations

import math

import pygame

from settings import (
    ASSETS_DIR,
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    FONT_PATH_SMALL,
    TARGET_FPS,
    TITLE_BG_IMAGE_PATH,
    WINDOW_SIZE,
)
from .common import _draw_rounded_rect, _load_font

CREDITS_TEAM = [
    {
        "name": "Kamdeu Yamdjeuson",
        "role": "Lead Engineer & Network Systems Developer",
        "portrait": str(ASSETS_DIR / "Characters" / "portait" / "Ninja.png"),
    },
]

CREDITS_THIRD_PARTY = [
    ("Pygame 2.6", "Game engine, display & audio framework"),
    ("PyTMX", "Tiled map file (.tmx) parser"),
    ("MiniUPnP", "UPnP / NAT traversal support"),
    ("Requests", "HTTP client for backend API calls"),
    ("Python-dotenv", "Environment variable management"),
]

CREDITS_SPECIAL_THANKS = [
    "The Pygame community for documentation and examples",
    "Tiled Map Editor for level design tooling",
    "All playtesters and early supporters of Grid Survival",
]

GAME_VERSION = "v1.0"
GAME_YEAR = "2025"

_PANEL_BG = (14, 20, 38, 230)
_PANEL_BORDER = (90, 140, 220)
_GOLD = (255, 215, 80)
_BLUE_LIGHT = (140, 200, 255)
_TEXT_MAIN = (240, 248, 255)
_TEXT_DIM = (165, 185, 215)
_TEXT_ROLE = (160, 200, 245)


class CreditsScreen:
    """Full-screen scrollable credits screen.

    Accessible from the title screen and the post-match summary.
    Call ``run()`` to block until the user presses ESC or clicks Back.
    """

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock) -> None:
        self.screen = screen
        self.clock = clock
        self.width, self.height = WINDOW_SIZE

        self._font_heading = _load_font(FONT_PATH_HEADING, 28, bold=True)
        self._font_section = _load_font(FONT_PATH_HEADING, 18, bold=True)
        self._font_name = _load_font(FONT_PATH_BODY, 20, bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, 17)
        self._font_small = _load_font(FONT_PATH_SMALL, 14)

        self._time = 0.0
        self._scroll_y = 0.0
        self._auto_scroll = True
        self._scroll_speed = 55.0

        self._back_rect = pygame.Rect(0, 0, 140, 44)
        self._back_rect.bottomleft = (28, self.height - 20)

        self._portraits: list[pygame.Surface | None] = [
            self._load_portrait(m["portrait"]) for m in CREDITS_TEAM
        ]
        self._bg_image = self._load_bg()

    def _load_bg(self) -> pygame.Surface | None:
        if not TITLE_BG_IMAGE_PATH.exists():
            return None
        try:
            raw = pygame.image.load(str(TITLE_BG_IMAGE_PATH)).convert()
            iw, ih = raw.get_size()
            scale = max(self.width / iw, self.height / ih)
            nw, nh = int(iw * scale), int(ih * scale)
            scaled = pygame.transform.smoothscale(raw, (nw, nh))
            cx = (nw - self.width) // 2
            cy = (nh - self.height) // 2
            return scaled.subsurface((cx, cy, self.width, self.height))
        except Exception:
            return None

    def _load_portrait(self, path: str) -> pygame.Surface | None:
        try:
            raw = pygame.image.load(path).convert_alpha()
            target = 110
            w, h = raw.get_size()
            scale = target / max(w, h)
            return pygame.transform.smoothscale(raw, (int(w * scale), int(h * scale)))
        except Exception:
            return None

    def run(self) -> None:
        self._scroll_y = 0.0
        self._time = 0.0
        self._auto_scroll = True

        total_h = self._content_height()
        max_scroll = max(0, total_h - self.height + 120)

        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._time += dt

            if self._auto_scroll:
                self._scroll_y += self._scroll_speed * dt
                if self._scroll_y >= max_scroll:
                    self._scroll_y = max_scroll
                    self._auto_scroll = False

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return
                    if event.key in (pygame.K_DOWN, pygame.K_s):
                        self._auto_scroll = False
                        self._scroll_y = min(self._scroll_y + 50, max_scroll)
                    if event.key in (pygame.K_UP, pygame.K_w):
                        self._auto_scroll = False
                        self._scroll_y = max(0.0, self._scroll_y - 50)
                    if event.key == pygame.K_SPACE:
                        self._auto_scroll = not self._auto_scroll
                if event.type == pygame.MOUSEWHEEL:
                    self._auto_scroll = False
                    self._scroll_y = max(0.0, min(self._scroll_y - event.y * 35, max_scroll))
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._back_rect.collidepoint(event.pos):
                        return

            self._draw()
            pygame.display.flip()

    def _content_height(self) -> int:
        h = 80
        h += 90
        h += 32
        h += 52
        h += len(CREDITS_TEAM) * 158
        h += 40
        h += 52
        h += len(CREDITS_THIRD_PARTY) * 52
        h += 40
        h += 52
        h += len(CREDITS_SPECIAL_THANKS) * 46
        h += 60
        h += 80
        return h

    def _draw(self) -> None:
        if self._bg_image:
            self.screen.blit(self._bg_image, (0, 0))
            veil = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            veil.fill((0, 0, 0, 185))
            self.screen.blit(veil, (0, 0))
        else:
            self.screen.fill((8, 12, 24))

        cx = self.width // 2
        content_w = min(880, self.width - 100)
        y = int(80 - self._scroll_y)

        y = self._draw_game_header(y, cx)
        y = self._draw_divider(y, cx, content_w, _GOLD, alpha=200)

        y = self._draw_section_label("DEVELOPMENT TEAM", y, cx, _BLUE_LIGHT)
        for idx, member in enumerate(CREDITS_TEAM):
            y = self._draw_member_card(member, self._portraits[idx], y, cx, content_w)

        y += 10
        y = self._draw_divider(y, cx, content_w, (80, 110, 160))

        y = self._draw_section_label("THIRD-PARTY LIBRARIES", y, cx, _BLUE_LIGHT)
        for lib_name, lib_desc in CREDITS_THIRD_PARTY:
            y = self._draw_lib_row(lib_name, lib_desc, y, cx, content_w)

        y += 10
        y = self._draw_divider(y, cx, content_w, (80, 110, 160))

        y = self._draw_section_label("SPECIAL THANKS", y, cx, _BLUE_LIGHT)
        for line in CREDITS_SPECIAL_THANKS:
            surf = self._font_small.render(f"•  {line}", True, _TEXT_DIM)
            self.screen.blit(surf, surf.get_rect(center=(cx, y + surf.get_height() // 2)))
            y += 46

        y += 20
        ver_surf = self._font_small.render(
            f"GRID SURVIVAL  {GAME_VERSION}  ©  {GAME_YEAR}  —  All rights reserved",
            True, (130, 148, 175),
        )
        self.screen.blit(ver_surf, ver_surf.get_rect(center=(cx, y + ver_surf.get_height() // 2)))

        self._draw_edge_fades()
        self._draw_hud()

    def _draw_game_header(self, y: int, cx: int) -> int:
        pulse = 1.0 + 0.025 * math.sin(self._time * 2.8)
        surf = self._font_heading.render("CREDITS", True, _GOLD)
        sw, sh = surf.get_size()
        scaled = pygame.transform.smoothscale(surf, (max(1, int(sw * pulse)), max(1, int(sh * pulse))))
        self.screen.blit(scaled, scaled.get_rect(center=(cx, y + scaled.get_height() // 2)))
        return y + 90

    def _draw_divider(self, y: int, cx: int, content_w: int, color: tuple, alpha: int = 140) -> int:
        line_surf = pygame.Surface((content_w, 2), pygame.SRCALPHA)
        line_surf.fill((*color[:3], alpha))
        self.screen.blit(line_surf, line_surf.get_rect(center=(cx, y)))
        return y + 22

    def _draw_section_label(self, text: str, y: int, cx: int, color: tuple) -> int:
        surf = self._font_section.render(text, True, color)
        self.screen.blit(surf, surf.get_rect(center=(cx, y + surf.get_height() // 2)))
        return y + 52

    def _draw_member_card(
        self,
        member: dict,
        portrait: pygame.Surface | None,
        y: int,
        cx: int,
        content_w: int,
    ) -> int:
        card_h = 140
        card_rect = pygame.Rect(cx - content_w // 2, y, content_w, card_h)

        glow_t = 0.5 + 0.5 * math.sin(self._time * 1.8)
        glow_alpha = int(18 + 14 * glow_t)
        glow_surf = pygame.Surface((card_rect.width + 16, card_rect.height + 16), pygame.SRCALPHA)
        pygame.draw.rect(
            glow_surf, (100, 160, 255, glow_alpha),
            glow_surf.get_rect(), border_radius=18,
        )
        self.screen.blit(glow_surf, (card_rect.left - 8, card_rect.top - 8))

        _draw_rounded_rect(self.screen, card_rect, _PANEL_BG, _PANEL_BORDER, 2, 14)

        avatar_cx = card_rect.left + 80
        avatar_cy = card_rect.centery
        avatar_r = 52

        pygame.draw.circle(self.screen, (30, 48, 80), (avatar_cx, avatar_cy), avatar_r)
        pygame.draw.circle(self.screen, (100, 160, 255), (avatar_cx, avatar_cy), avatar_r, 2)

        if portrait is not None:
            p_rect = portrait.get_rect(center=(avatar_cx, avatar_cy))
            clip = pygame.Surface((avatar_r * 2, avatar_r * 2), pygame.SRCALPHA)
            pygame.draw.circle(clip, (255, 255, 255, 255), (avatar_r, avatar_r), avatar_r)
            portrait_clipped = portrait.copy().convert_alpha()
            portrait_clipped.blit(clip, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            self.screen.blit(portrait_clipped, portrait_clipped.get_rect(center=(avatar_cx, avatar_cy)))

        text_x = card_rect.left + 160

        name_surf = self._font_name.render(member["name"], True, _TEXT_MAIN)
        self.screen.blit(name_surf, name_surf.get_rect(midleft=(text_x, avatar_cy - 18)))

        role_surf = self._font_small.render(member["role"], True, _TEXT_ROLE)
        self.screen.blit(role_surf, role_surf.get_rect(midleft=(text_x, avatar_cy + 18)))

        return y + card_h + 18

    def _draw_lib_row(self, lib_name: str, lib_desc: str, y: int, cx: int, content_w: int) -> int:
        row_rect = pygame.Rect(cx - content_w // 2, y, content_w, 44)
        _draw_rounded_rect(self.screen, row_rect, (18, 28, 50, 200), (65, 95, 145), 1, 8)

        name_surf = self._font_body.render(lib_name, True, (200, 228, 255))
        self.screen.blit(name_surf, name_surf.get_rect(midleft=(row_rect.left + 18, row_rect.centery)))

        desc_surf = self._font_small.render(lib_desc, True, _TEXT_DIM)
        self.screen.blit(desc_surf, desc_surf.get_rect(midright=(row_rect.right - 18, row_rect.centery)))

        return y + 52

    def _draw_edge_fades(self) -> None:
        fade_h = 80
        for top_y, going_in in ((0, True), (self.height - fade_h, False)):
            fade = pygame.Surface((self.width, fade_h), pygame.SRCALPHA)
            for row in range(fade_h):
                alpha = int(235 * (row / fade_h)) if going_in else int(235 * (1 - row / fade_h))
                pygame.draw.line(fade, (0, 0, 0, alpha), (0, row), (self.width, row))
            self.screen.blit(fade, (0, top_y))

    def _draw_hud(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        hovered = self._back_rect.collidepoint(mouse_pos)
        bg = (55, 35, 35, 230) if hovered else (38, 28, 28, 210)
        border = (220, 100, 100) if hovered else (150, 80, 80)
        _draw_rounded_rect(self.screen, self._back_rect, bg, border, 2, 10)
        label = self._font_small.render("BACK  (ESC)", True, (235, 215, 215))
        self.screen.blit(label, label.get_rect(center=self._back_rect.center))

        hint = self._font_small.render(
            "SCROLL / ↑↓ to navigate   •   SPACE to pause auto-scroll",
            True, (130, 148, 175),
        )
        self.screen.blit(hint, hint.get_rect(centerx=self.width // 2, bottom=self.height - 8))


__all__ = ["CreditsScreen"]
