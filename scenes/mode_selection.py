from __future__ import annotations

import math

import pygame

from settings import (
    WINDOW_SIZE,
    TARGET_FPS,
    SCENE_FADE_SPEED,
    SCENE_OVERLAY_COLOR,
    MODE_BG_COLOR,
    MODE_BG_IMAGE_PATH,
    MODE_HEADER_COLOR,
    MODE_HEADER_NAME_COLOR,
    MODE_SUBTITLE_COLOR,
    MODE_CARD_WIDTH,
    MODE_CARD_HEIGHT,
    MODE_CARD_SPACING,
    MODE_CARD_BASE_COLOR,
    MODE_CARD_HOVER_COLOR,
    MODE_CARD_TITLE_COLOR,
    MODE_CARD_DESC_COLOR,
    MODE_CARD_CLICK_BASE,
    MODE_CARD_BORDER_VS_COMPUTER,
    MODE_CARD_BORDER_LOCAL_MP,
    MODE_CARD_BORDER_ONLINE_MP,
    MODE_CARD_HOVER_BORDER_VS_COMPUTER,
    MODE_CARD_HOVER_BORDER_LOCAL_MP,
    MODE_CARD_HOVER_BORDER_ONLINE_MP,
    MODE_CLICK_FLASH_TIME,
    MODE_HEADER_SLIDE_DURATION,
    MODE_HEADER_SLIDE_DISTANCE,
    MODE_SUBTITLE_DELAY,
    MODE_VS_COMPUTER,
    MODE_LOCAL_MULTIPLAYER,
    MODE_ONLINE_MULTIPLAYER,
    FONT_PATH_HEADING,
    FONT_PATH_BODY,
    FONT_PATH_SMALL,
    FONT_SIZE_HEADING,
    FONT_SIZE_BODY,
    FONT_SIZE_SMALL,
)
from .common import _draw_rounded_rect, _load_font


class ModeSelectionScreen:
    """Mode select screen shown after successful name entry."""

    _MODE_ICONS = {
        MODE_VS_COMPUTER: "🤖",
        MODE_LOCAL_MULTIPLAYER: "🎮",
        MODE_ONLINE_MULTIPLAYER: "🌐",
    }

    _MODE_BORDER = {
        MODE_VS_COMPUTER: MODE_CARD_BORDER_VS_COMPUTER,
        MODE_LOCAL_MULTIPLAYER: MODE_CARD_BORDER_LOCAL_MP,
        MODE_ONLINE_MULTIPLAYER: MODE_CARD_BORDER_ONLINE_MP,
    }

    _MODE_HOVER_BORDER = {
        MODE_VS_COMPUTER: MODE_CARD_HOVER_BORDER_VS_COMPUTER,
        MODE_LOCAL_MULTIPLAYER: MODE_CARD_HOVER_BORDER_LOCAL_MP,
        MODE_ONLINE_MULTIPLAYER: MODE_CARD_HOVER_BORDER_ONLINE_MP,
    }

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock, player_name: str):
        self.screen = screen
        self.clock = clock
        self.player_name = player_name
        self.width, self.height = WINDOW_SIZE
        self.back_requested = False
        self.quit_requested = False

        # Font hierarchy
        self._font_heading = _load_font(FONT_PATH_HEADING, FONT_SIZE_HEADING, bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, FONT_SIZE_BODY)
        self._font_small = _load_font(FONT_PATH_SMALL, FONT_SIZE_SMALL)
        self._font_card_title = _load_font(FONT_PATH_HEADING, 22, bold=True)
        self._font_card_desc = _load_font(FONT_PATH_BODY, 16)
        self._font_header = _load_font(FONT_PATH_HEADING, 36, bold=True)
        self._font_icon = pygame.font.SysFont("segoe ui emoji", 40)

        # Header animation state
        self._anim_time = 0.0
        self._header_alpha = 0.0
        self._header_y_offset = MODE_HEADER_SLIDE_DISTANCE
        self._subtitle_alpha = 0.0
        self._subtitle_visible = False

        # Card hover animation (smooth y offset per card)
        card_w = MODE_CARD_WIDTH
        card_h = MODE_CARD_HEIGHT
        gap = 34
        total_h = 3 * card_h + 2 * gap
        start_y = (self.height - total_h) // 2 + 60

        self.cards = [
            {
                "mode": MODE_VS_COMPUTER,
                "title": "VS COMPUTER",
                "desc": "Face an AI-controlled opponent",
                "key": "[1]",
                "rect": pygame.Rect(0, start_y + (card_h + gap) * 0, card_w, card_h),
                "hover_y": 0.0,
                "click_scale": 1.0,
                "click_timer": 0.0,
            },
            {
                "mode": MODE_LOCAL_MULTIPLAYER,
                "title": "LOCAL MULTIPLAYER",
                "desc": "Play with another player on this keyboard",
                "key": "[2]",
                "rect": pygame.Rect(0, start_y + (card_h + gap) * 1, card_w, card_h),
                "hover_y": 0.0,
                "click_scale": 1.0,
                "click_timer": 0.0,
            },
            {
                "mode": MODE_ONLINE_MULTIPLAYER,
                "title": "LAN MULTIPLAYER (HOST/JOIN)",
                "desc": "Play with others on your local network (LAN)",
                "key": "[3]",
                "rect": pygame.Rect(0, start_y + (card_h + gap) * 2, card_w, card_h),
                "hover_y": 0.0,
                "click_scale": 1.0,
                "click_timer": 0.0,
            },
        ]
        for card in self.cards:
            card["rect"].centerx = self.width // 2

        self._clicked_mode = None
        self._flash_timer = 0.0

        # Load background
        self._bg_image = None
        if MODE_BG_IMAGE_PATH.exists():
            try:
                raw_bg = pygame.image.load(str(MODE_BG_IMAGE_PATH)).convert()
                # Scale using the same cover logic
                img_w, img_h = raw_bg.get_size()
                scale_w = self.width / img_w
                scale_h = self.height / img_h
                scale = max(scale_w, scale_h)
                new_w, new_h = int(img_w * scale), int(img_h * scale)
                scaled_bg = pygame.transform.smoothscale(raw_bg, (new_w, new_h))
                crop_x = (new_w - self.width) // 2
                crop_y = (new_h - self.height) // 2
                self._bg_image = scaled_bg.subsurface((crop_x, crop_y, self.width, self.height))
            except Exception as e:
                print(f"Failed to load mode bg: {e}")

        self._back_button_rect = pygame.Rect(24, self.height - 72, 160, 48)

    def _update_animations(self, dt: float):
        self._anim_time += dt

        progress = min(1.0, self._anim_time / MODE_HEADER_SLIDE_DURATION)
        ease = 1 - (1 - progress) ** 3
        self._header_y_offset = MODE_HEADER_SLIDE_DISTANCE * (1.0 - ease)
        self._header_alpha = min(255.0, 255 * ease)

        if self._anim_time >= MODE_HEADER_SLIDE_DURATION + MODE_SUBTITLE_DELAY:
            sub_progress = min(1.0, (self._anim_time - MODE_HEADER_SLIDE_DURATION - MODE_SUBTITLE_DELAY) / 0.5)
            self._subtitle_alpha = min(255.0, 255 * sub_progress)

        mouse_pos = pygame.mouse.get_pos()
        for card in self.cards:
            hovered = card["rect"].collidepoint(mouse_pos)
            target_y = -4.0 if hovered else 0.0
            card["hover_y"] += (target_y - card["hover_y"]) * min(1.0, dt * 12)

            if card["click_timer"] > 0:
                card["click_timer"] -= dt
                t = max(0.0, card["click_timer"] / 0.1)
                card["click_scale"] = 1.0 - 0.05 * t
            else:
                card["click_scale"] = 1.0

    def _draw(self) -> None:
        if self._bg_image:
            self.screen.blit(self._bg_image, (0, 0))
            # Overlay
            overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 115))  # 45% black
            self.screen.blit(overlay, (0, 0))
        else:
            self.screen.fill(MODE_BG_COLOR)

        header_y = int(80 + self._header_y_offset)
        welcome_str = "Welcome, "
        name_str = self.player_name + "!"
        welcome_surf = self._font_header.render(welcome_str, True, MODE_HEADER_COLOR)
        name_surf = self._font_header.render(name_str, True, MODE_HEADER_NAME_COLOR)
        total_w = welcome_surf.get_width() + name_surf.get_width()
        start_x = self.width // 2 - total_w // 2

        welcome_surf.set_alpha(int(self._header_alpha))
        name_surf.set_alpha(int(self._header_alpha))
        self.screen.blit(welcome_surf, (start_x, header_y))
        self.screen.blit(name_surf, (start_x + welcome_surf.get_width(), header_y))

        subtitle_surf = self._font_body.render("CHOOSE YOUR GAME MODE", True, MODE_SUBTITLE_COLOR)
        subtitle_surf.set_alpha(int(self._subtitle_alpha))
        self.screen.blit(subtitle_surf, subtitle_surf.get_rect(center=(self.width // 2, header_y + 55)))

        self._draw_back_button()

        mouse_pos = pygame.mouse.get_pos()
        for card in self.cards:
            self._draw_card(card, mouse_pos)

    def _draw_back_button(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        hovered = self._back_button_rect.collidepoint(mouse_pos)
        base_color = (30, 38, 60, 220)
        hover_color = (60, 78, 110, 235)
        bg_color = hover_color if hovered else base_color
        border_color = (120, 150, 200)
        _draw_rounded_rect(self.screen, self._back_button_rect, bg_color, border_color, 2, 14)
        label = self._font_small.render("BACK", True, (235, 235, 245))
        self.screen.blit(label, label.get_rect(center=self._back_button_rect.center))

    def _draw_card(self, card: dict, mouse_pos: tuple) -> None:
        rect = card["rect"].copy()
        rect.y += int(card["hover_y"])

        hovered = rect.collidepoint(mouse_pos)
        selected = self._clicked_mode == card["mode"]
        mode = card["mode"]

        if selected:
            pulse = 0.5 + 0.5 * math.sin(self._flash_timer * 20)
            bg_r = int(MODE_CARD_CLICK_BASE[0] + 80 * pulse)
            bg_g = int(MODE_CARD_CLICK_BASE[1] + 80 * pulse)
            bg_b = int(MODE_CARD_CLICK_BASE[2] + 40 * pulse)
            bg_color = (bg_r, bg_g, bg_b, 230)
        elif hovered:
            bg_color = MODE_CARD_HOVER_COLOR
        else:
            bg_color = MODE_CARD_BASE_COLOR

        if hovered or selected:
            border_color = self._MODE_HOVER_BORDER[mode]
            border_w = 3
        else:
            border_color = self._MODE_BORDER[mode]
            border_w = 2

        if card["click_scale"] != 1.0:
            s = card["click_scale"]
            new_w = int(rect.width * s)
            new_h = int(rect.height * s)
            rect = pygame.Rect(
                rect.centerx - new_w // 2,
                rect.centery - new_h // 2,
                new_w, new_h
            )

        _draw_rounded_rect(self.screen, rect, bg_color, border_color, border_w, 16)

        if selected:
            flash_pulse = 0.5 + 0.5 * math.sin(self._flash_timer * 30)
            if flash_pulse > 0.8:
                flash_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
                pygame.draw.rect(flash_surf, (255, 255, 255, 40), flash_surf.get_rect(), border_radius=16)
                self.screen.blit(flash_surf, rect.topleft)

        icon_str = self._MODE_ICONS.get(card["mode"], "?")
        try:
            icon_surf = self._font_icon.render(icon_str, True, (255, 255, 255))
        except Exception:
            icon_surf = self._font_body.render(icon_str, True, (255, 255, 255))
        icon_rect = icon_surf.get_rect(centerx=rect.centerx, top=rect.top + 18)
        self.screen.blit(icon_surf, icon_rect)

        title_color = border_color if hovered else MODE_CARD_TITLE_COLOR
        title_surf = self._font_card_title.render(card["title"], True, title_color)
        title_rect = title_surf.get_rect(centerx=rect.centerx, top=icon_rect.bottom + 10)
        self.screen.blit(title_surf, title_rect)

        desc_surf = self._font_card_desc.render(card["desc"], True, MODE_CARD_DESC_COLOR)
        desc_rect = desc_surf.get_rect(centerx=rect.centerx, top=title_rect.bottom + 8)
        self.screen.blit(desc_surf, desc_rect)

        key_surf = self._font_small.render(card["key"], True, border_color)
        key_rect = key_surf.get_rect(right=rect.right - 12, bottom=rect.bottom - 10)
        self.screen.blit(key_surf, key_rect)

    def _fade(self, fade_in: bool) -> None:
        overlay = pygame.Surface(WINDOW_SIZE)
        alpha = 255 if fade_in else 0

        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            step = SCENE_FADE_SPEED * dt
            if fade_in:
                alpha -= step
                if alpha <= 0:
                    break
            else:
                alpha += step
                if alpha >= 255:
                    alpha = 255
                    break

            self._update_animations(dt)
            self._draw()
            overlay.fill(SCENE_OVERLAY_COLOR)
            overlay.set_alpha(int(alpha))
            self.screen.blit(overlay, (0, 0))
            pygame.display.flip()

    def run(self):
        self._fade(True)

        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._flash_timer += dt
            self._update_animations(dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit_requested = True
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        self.back_requested = True
                        return None
                    if event.key == pygame.K_1:
                        self._clicked_mode = MODE_VS_COMPUTER
                        self.cards[0]["click_timer"] = 0.1
                    elif event.key == pygame.K_2:
                        self._clicked_mode = MODE_LOCAL_MULTIPLAYER
                        self.cards[1]["click_timer"] = 0.1
                    elif event.key == pygame.K_3:
                        self._clicked_mode = MODE_ONLINE_MULTIPLAYER
                        self.cards[2]["click_timer"] = 0.1
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._back_button_rect.collidepoint(event.pos):
                        self.back_requested = True
                        return None
                    for card in self.cards:
                        hover_rect = card["rect"].copy()
                        hover_rect.y += int(card["hover_y"])
                        if hover_rect.collidepoint(event.pos):
                            self._clicked_mode = card["mode"]
                            card["click_timer"] = 0.1
                            break

            self._draw()
            pygame.display.flip()

            if self._clicked_mode is not None:
                flash_elapsed = 0.0
                while flash_elapsed < MODE_CLICK_FLASH_TIME:
                    fdt = self.clock.tick(TARGET_FPS) / 1000.0
                    flash_elapsed += fdt
                    self._flash_timer += fdt
                    self._update_animations(fdt)
                    self._draw()
                    pygame.display.flip()

                self._fade(False)
                return self._clicked_mode


__all__ = ["ModeSelectionScreen"]
