from __future__ import annotations

import math

import pygame

from settings import (
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    FONT_PATH_SMALL,
    FONT_SIZE_BODY,
    FONT_SIZE_HEADING,
    FONT_SIZE_SMALL,
    MODE_BG_COLOR,
    MODE_BG_IMAGE_PATH,
    MODE_CARD_BASE_COLOR,
    MODE_CARD_BORDER_ONLINE_MP,
    MODE_CARD_HOVER_BORDER_ONLINE_MP,
    MODE_CARD_HOVER_COLOR,
    SCENE_FADE_SPEED,
    SCENE_OVERLAY_COLOR,
    TARGET_FPS,
    WINDOW_SIZE,
)
from .common import SceneAudioOverlay, _draw_rounded_rect, _load_font


class TargetScoreSelectionScreen:
    """Choose how many round wins are needed to win the match."""

    TARGET_OPTIONS = [3, 5, 10, 15, 20]

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        self.screen = screen
        self.clock = clock
        self.width, self.height = WINDOW_SIZE
        self.quit_requested = False
        self._audio_overlay = SceneAudioOverlay()

        self._font_header = _load_font(FONT_PATH_HEADING, max(28, FONT_SIZE_HEADING + 4), bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, FONT_SIZE_BODY)
        self._font_small = _load_font(FONT_PATH_SMALL, FONT_SIZE_SMALL)
        self._font_number = _load_font(FONT_PATH_HEADING, 46, bold=True)

        self._selected_index = 0
        self._hover_index: int | None = None
        self._anim_time = 0.0

        self._back_button_rect = pygame.Rect(24, self.height - 72, 160, 48)

        self._bg_image = None
        if MODE_BG_IMAGE_PATH.exists():
            try:
                raw_bg = pygame.image.load(str(MODE_BG_IMAGE_PATH)).convert()
                img_w, img_h = raw_bg.get_size()
                scale_w = self.width / img_w
                scale_h = self.height / img_h
                scale = max(scale_w, scale_h)
                new_w, new_h = int(img_w * scale), int(img_h * scale)
                scaled_bg = pygame.transform.smoothscale(raw_bg, (new_w, new_h))
                crop_x = (new_w - self.width) // 2
                crop_y = (new_h - self.height) // 2
                self._bg_image = scaled_bg.subsurface((crop_x, crop_y, self.width, self.height))
            except Exception:
                self._bg_image = None

        self._cards = self._build_cards()

    def _build_cards(self) -> list[dict]:
        card_w = 132
        card_h = 140
        gap_x = 22
        gap_y = 24

        cols = max(1, min(5, self.width // (card_w + gap_x)))
        rows = max(1, math.ceil(len(self.TARGET_OPTIONS) / cols))

        total_w = cols * card_w + (cols - 1) * gap_x
        total_h = rows * card_h + (rows - 1) * gap_y

        top_margin = 190
        bottom_margin = 130
        available_h = max(1, self.height - top_margin - bottom_margin)

        start_x = (self.width - total_w) // 2
        start_y = top_margin + max(0, (available_h - total_h) // 2)

        cards: list[dict] = []
        for idx, target in enumerate(self.TARGET_OPTIONS):
            row = idx // cols
            col = idx % cols
            rect = pygame.Rect(
                start_x + col * (card_w + gap_x),
                start_y + row * (card_h + gap_y),
                card_w,
                card_h,
            )
            cards.append({"index": idx, "rect": rect, "target": target, "cols": cols})

        return cards

    def _draw_background(self) -> None:
        if self._bg_image:
            self.screen.blit(self._bg_image, (0, 0))
            overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            self.screen.blit(overlay, (0, 0))
        else:
            self.screen.fill(MODE_BG_COLOR)

    def _draw_header(self) -> None:
        title = self._font_header.render("TARGET SCORE", True, (255, 255, 255))
        subtitle = self._font_body.render(
            "First player to this many round wins takes the match",
            True,
            (205, 215, 235),
        )

        self.screen.blit(title, title.get_rect(center=(self.width // 2, 82)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(self.width // 2, 128)))

    def _draw_back_button(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        hovered = self._back_button_rect.collidepoint(mouse_pos)
        bg_color = (60, 78, 110, 235) if hovered else (30, 38, 60, 220)
        border_color = (120, 150, 200)
        _draw_rounded_rect(self.screen, self._back_button_rect, bg_color, border_color, 2, 14)
        label = self._font_small.render("BACK", True, (235, 235, 245))
        self.screen.blit(label, label.get_rect(center=self._back_button_rect.center))

    def _draw_cards(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        self._hover_index = None

        for card in self._cards:
            idx = card["index"]
            target = card["target"]
            rect = card["rect"].copy()

            hovered = rect.collidepoint(mouse_pos)
            selected = idx == self._selected_index
            if hovered:
                self._hover_index = idx
                rect.y -= 2

            if selected:
                pulse = 0.5 + 0.5 * math.sin(self._anim_time * 6.2)
                border = (95, 225, 255)
                glow = pygame.Surface((rect.width + 18, rect.height + 18), pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (95, 225, 255, int(28 + 28 * pulse)),
                    glow.get_rect(),
                    border_radius=16,
                )
                self.screen.blit(glow, (rect.left - 9, rect.top - 9), special_flags=pygame.BLEND_ADD)
            elif hovered:
                border = MODE_CARD_HOVER_BORDER_ONLINE_MP
            else:
                border = MODE_CARD_BORDER_ONLINE_MP

            _draw_rounded_rect(
                self.screen,
                rect,
                MODE_CARD_HOVER_COLOR if hovered else MODE_CARD_BASE_COLOR,
                border,
                3 if (hovered or selected) else 2,
                14,
            )

            value_text = self._font_number.render(str(target), True, (240, 246, 255))
            value_rect = value_text.get_rect(center=(rect.centerx, rect.centery - 18))
            self.screen.blit(value_text, value_rect)

            wins_text = self._font_small.render("ROUND WINS", True, (190, 205, 225))
            wins_rect = wins_text.get_rect(center=(rect.centerx, rect.bottom - 28))
            self.screen.blit(wins_text, wins_rect)

    def _draw(self) -> None:
        self._draw_background()
        self._draw_header()
        self._draw_cards()
        self._draw_back_button()
        self._audio_overlay.draw(self.screen)

    def _fade(self, fade_in: bool) -> None:
        overlay = pygame.Surface(WINDOW_SIZE)
        alpha = 255 if fade_in else 0
        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._anim_time += dt
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

            self._draw()
            overlay.fill(SCENE_OVERLAY_COLOR)
            overlay.set_alpha(int(alpha))
            self.screen.blit(overlay, (0, 0))
            pygame.display.flip()

    def _move_selection(self, delta_row: int, delta_col: int) -> None:
        if not self._cards:
            return

        cols = self._cards[0]["cols"] if self._cards else 1
        idx = self._selected_index
        row = idx // cols
        col = idx % cols

        row += delta_row
        col += delta_col

        if col < 0:
            col = cols - 1
        elif col >= cols:
            col = 0

        max_row = math.ceil(len(self._cards) / cols) - 1
        if row < 0:
            row = max_row
        elif row > max_row:
            row = 0

        candidate = row * cols + col
        while candidate >= len(self._cards) and col > 0:
            col -= 1
            candidate = row * cols + col

        self._selected_index = max(0, min(len(self._cards) - 1, candidate))

    def run(self) -> int | None:
        self._fade(True)

        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._anim_time += dt

            for event in pygame.event.get():
                if self._audio_overlay.handle_event(event):
                    continue
                if event.type == pygame.QUIT:
                    self.quit_requested = True
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        return None
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self._fade(False)
                        return int(self.TARGET_OPTIONS[self._selected_index])
                    if event.key in (pygame.K_LEFT, pygame.K_a):
                        self._move_selection(0, -1)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        self._move_selection(0, 1)
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        self._move_selection(-1, 0)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self._move_selection(1, 0)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._back_button_rect.collidepoint(event.pos):
                        return None
                    for card in self._cards:
                        if card["rect"].collidepoint(event.pos):
                            self._selected_index = card["index"]
                            self._fade(False)
                            return int(self.TARGET_OPTIONS[self._selected_index])

            if self._hover_index is not None:
                self._selected_index = self._hover_index

            self._draw()
            pygame.display.flip()


__all__ = ["TargetScoreSelectionScreen"]
