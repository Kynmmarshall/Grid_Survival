from __future__ import annotations

import math
import random

import pygame

from level_config import get_level, MAX_LEVEL
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
    MODE_CARD_BORDER_STORY,
    MODE_CARD_HOVER_BORDER_STORY,
    MODE_CLICK_FLASH_TIME,
    MODE_HEADER_SLIDE_DURATION,
    MODE_HEADER_SLIDE_DISTANCE,
    MODE_SUBTITLE_DELAY,
    FONT_PATH_HEADING,
    FONT_PATH_BODY,
    FONT_PATH_SMALL,
    FONT_SIZE_HEADING,
    FONT_SIZE_BODY,
    FONT_SIZE_SMALL,
)
from .common import SceneAudioOverlay, _draw_rounded_rect, _load_font


class LevelSelectionScreen:
    """Level select screen for Story Mode."""

    _LEVEL_ICONS = {i: str(i) for i in range(1, MAX_LEVEL + 1)}

    _LEVEL_BORDER = {i: MODE_CARD_BORDER_STORY for i in range(1, MAX_LEVEL + 1)}

    _LEVEL_HOVER_BORDER = {i: MODE_CARD_HOVER_BORDER_STORY for i in range(1, MAX_LEVEL + 1)}

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock, player_name: str, max_unlocked_level: int = MAX_LEVEL):
        self.screen = screen
        self.clock = clock
        self.player_name = player_name
        self.width, self.height = WINDOW_SIZE
        self.back_requested = False
        self.quit_requested = False
        self._audio_overlay = SceneAudioOverlay()
        self.max_unlocked_level = max_unlocked_level

        # Font hierarchy
        self._font_heading = _load_font(FONT_PATH_HEADING, FONT_SIZE_HEADING, bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, FONT_SIZE_BODY)
        self._font_small = _load_font(FONT_PATH_SMALL, FONT_SIZE_SMALL)
        self._font_card_title = _load_font(FONT_PATH_HEADING, 20, bold=True)
        self._font_card_desc = _load_font(FONT_PATH_BODY, 14)
        self._font_header = _load_font(FONT_PATH_HEADING, 36, bold=True)
        self._font_icon = pygame.font.SysFont("segoe ui emoji", 36)

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
        cols = 3
        rows = 3
        total_w = cols * card_w + (cols - 1) * gap
        total_h = rows * card_h + (rows - 1) * gap
        start_x = (self.width - total_w) // 2
        start_y = (self.height - total_h) // 2 + 80

        short_desc = {
            1: "1 AI, full arena",
            2: "2 AIs, L-shape",
            3: "3 AIs, cross",
            4: "4 AIs, ring",
            5: "5 AIs, bridges",
            6: "6 AIs, islands",
            7: "7 AIs, full",
            8: "8 AIs, abyss",
            9: "9 AIs, nightmare"
        }

        self.cards = []
        for i in range(1, MAX_LEVEL + 1):
            level_config = get_level(i)
            row = (i - 1) // cols
            col = (i - 1) % cols
            rect = pygame.Rect(
                start_x + col * (card_w + gap),
                start_y + row * (card_h + gap),
                card_w,
                card_h,
            )
            self.cards.append({
                "level": i,
                "title": f"Level {i}: {level_config.name}",
                "desc": short_desc.get(i, level_config.description),
                "key": f"[{i}]",
                "rect": rect,
                "hover_y": 0.0,
                "click_scale": 1.0,
                "click_timer": 0.0,
            })
        for card in self.cards:
            card["rect"].centerx = card["rect"].centerx  # already centered

        self._clicked_level = None
        self._flash_timer = 0.0

        self._bg_particles = []
        for _ in range(42):
            self._bg_particles.append({
                "x": random.uniform(0, self.width),
                "y": random.uniform(0, self.height),
                "radius": random.uniform(1.5, 4.5),
                "speed": random.uniform(6.0, 20.0),
                "drift": random.uniform(-18.0, 18.0),
                "phase": random.uniform(0, math.tau),
                "color": random.choice([
                    (90, 180, 255),
                    (120, 240, 190),
                    (180, 120, 255),
                    (255, 200, 120),
                ]),
            })
        self._bg_sweep_offset = 0.0
        self._bg_grid_offset = 0.0
        self.cards = []

        for i in range(1, MAX_LEVEL + 1):
            level_config = get_level(i)
            row = (i - 1) // cols
            col = (i - 1) % cols
            rect = pygame.Rect(
                start_x + col * (card_w + gap),
                start_y + row * (card_h + gap),
                card_w,
                card_h,
            )
            locked = i > self.max_unlocked_level
            self.cards.append({
                "level": i,
                "title": f"Level {i}: {level_config.name}" if not locked else f"Level {i}: Locked",
                "desc": short_desc.get(i, level_config.description) if not locked else "Complete previous levels to unlock",
                "key": f"[{i}]" if not locked else "",
                "rect": rect,
                "hover_y": 0.0,
                "click_scale": 1.0,
                "click_timer": 0.0,
                "locked": locked,
            })
        for card in self.cards:
            card["rect"].centerx = card["rect"].centerx  # already centered

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
        self._bg_sweep_offset = (self._bg_sweep_offset + 120 * dt) % (self.width + 320)
        self._bg_grid_offset = (self._bg_grid_offset + 18 * dt) % 48

        for particle in self._bg_particles:
            particle["y"] -= particle["speed"] * dt
            particle["x"] += math.sin(self._anim_time * 0.8 + particle["phase"]) * particle["drift"] * dt
            if particle["y"] < -20:
                particle["y"] = self.height + 20
                particle["x"] = random.uniform(0, self.width)
            elif particle["y"] > self.height + 20:
                particle["y"] = -20
                particle["x"] = random.uniform(0, self.width)

            if particle["x"] < -20:
                particle["x"] = self.width + 20
            elif particle["x"] > self.width + 20:
                particle["x"] = -20

    def run(self) -> int | None:
        """Run the level selection screen. Returns selected level number or None if back/quit."""
        running = True
        selected_level = None

        while running:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._update_animations(dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.quit_requested = True
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        if self._handle_card_click(event.pos):
                            selected_level = self._clicked_level
                            running = False
                        elif self._back_button_rect.collidepoint(event.pos):
                            self.back_requested = True
                            running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.back_requested = True
                        running = False
                    elif pygame.K_1 <= event.key <= pygame.K_9:
                        level = event.key - pygame.K_0
                        if 1 <= level <= MAX_LEVEL and level <= self.max_unlocked_level:
                            selected_level = level
                            running = False

            self._draw()
            pygame.display.flip()

        return selected_level

    def _handle_card_click(self, pos: tuple[int, int]) -> bool:
        for card in self.cards:
            if card["rect"].collidepoint(pos) and not card.get("locked", False):
                self._clicked_level = card["level"]
                card["click_timer"] = MODE_CLICK_FLASH_TIME
                return True
        return False

    def _draw(self):
        self._draw_background()
        self._draw_header()
        self._draw_cards()
        self._draw_buttons()

    def _draw_background(self):
        if self._bg_image:
            self.screen.blit(self._bg_image, (0, 0))

        # Grid overlay
        grid_color = (50, 60, 80, 30)
        for x in range(0, self.width, 48):
            pygame.draw.line(self.screen, grid_color, (x + self._bg_grid_offset, 0), (x + self._bg_grid_offset, self.height))
        for y in range(0, self.height, 48):
            pygame.draw.line(self.screen, grid_color, (0, y + self._bg_grid_offset), (self.width, y + self._bg_grid_offset))

        # Particles
        for p in self._bg_particles:
            pygame.draw.circle(self.screen, (*p["color"], 120), (int(p["x"]), int(p["y"])), int(p["radius"]))

    def _draw_header(self):
        # Header slide animation
        self._header_y_offset = max(0, self._header_y_offset - MODE_HEADER_SLIDE_DISTANCE * (1 / MODE_HEADER_SLIDE_DURATION) * (self.clock.get_time() / 1000.0))
        header_y = 40 + self._header_y_offset
        self._header_alpha = min(255, self._header_alpha + SCENE_FADE_SPEED * (self.clock.get_time() / 1000.0))

        # Main Title
        title_surf = self._font_heading.render("SELECT LEVEL", True, MODE_HEADER_COLOR)
        title_surf.set_alpha(int(self._header_alpha))
        title_rect = title_surf.get_rect(center=(self.width // 2, header_y))
        self.screen.blit(title_surf, title_rect)

        # Subtitle
        if self._header_y_offset <= 0:
            self._subtitle_visible = True
        if self._subtitle_visible:
            self._subtitle_alpha = min(255, self._subtitle_alpha + SCENE_FADE_SPEED * (self.clock.get_time() / 1000.0))
            subtitle_surf = self._font_body.render(f"Welcome, {self.player_name}!", True, MODE_SUBTITLE_COLOR)
            subtitle_surf.set_alpha(int(self._subtitle_alpha))
            self.screen.blit(subtitle_surf, subtitle_surf.get_rect(center=(self.width // 2, header_y + 50)))

    def _draw_cards(self):
        mouse_pos = pygame.mouse.get_pos()

        for card in self.cards:
            level = card["level"]
            rect = card["rect"]
            hovered = rect.collidepoint(mouse_pos)

            scale = 1.0
            if card["click_timer"] > 0:
                card["click_timer"] -= self.clock.get_time() / 1000.0
                scale = 1.0 + (card["click_timer"] / MODE_CLICK_FLASH_TIME) * 0.1
            elif hovered:
                scale = 1.05

            if scale != 1.0:
                w = int(rect.width * scale)
                h = int(rect.height * scale)
                draw_rect = pygame.Rect(0, 0, w, h)
                draw_rect.center = rect.center
            else:
                draw_rect = rect.copy()

            # Background
            locked = card.get("locked", False)
            if locked:
                bg_color = (50, 50, 50, 200)
                border_color = (100, 100, 100)
                text_color = (150, 150, 150)
            else:
                bg_color = MODE_CARD_BASE_COLOR if not hovered else MODE_CARD_HOVER_COLOR
                border_color = self._LEVEL_BORDER[level]
                text_color = MODE_CARD_TITLE_COLOR
            _draw_rounded_rect(self.screen, draw_rect, bg_color, border_color, 2, 12)

            # Title
            title_surf = self._font_card_title.render(card["title"], True, text_color)
            title_rect = title_surf.get_rect(midtop=(draw_rect.centerx, draw_rect.top + 15))
            self.screen.blit(title_surf, title_rect)

            # Icon
            if not locked:
                icon_surf = self._font_icon.render(self._LEVEL_ICONS[level], True, text_color)
                icon_rect = icon_surf.get_rect(midtop=(draw_rect.centerx, title_rect.bottom + 10))
                self.screen.blit(icon_surf, icon_rect)
                y_start = icon_rect.bottom + 15
            else:
                y_start = title_rect.bottom + 20

            # Description
            desc_lines = card["desc"].split('\n')
            y = y_start
            for line in desc_lines:
                line_surf = self._font_card_desc.render(line, True, text_color)
                line_rect = line_surf.get_rect(midtop=(draw_rect.centerx, y))
                self.screen.blit(line_surf, line_rect)
                y += 18

            # Key hint
            if not locked:
                key_surf = self._font_small.render(card["key"], True, MODE_CARD_DESC_COLOR)
                key_rect = key_surf.get_rect(midbottom=(draw_rect.centerx, draw_rect.bottom - 10))
                self.screen.blit(key_surf, key_rect)

    def _draw_buttons(self):
        # Back button
        back_color = (60, 70, 90)
        back_hover = (80, 90, 110)
        mouse_pos = pygame.mouse.get_pos()
        hovered = self._back_button_rect.collidepoint(mouse_pos)
        _draw_rounded_rect(self.screen, self._back_button_rect, back_hover if hovered else back_color, (200, 200, 200), 2, 12)
        back_text = self._font_small.render("BACK", True, (255, 255, 255))
        self.screen.blit(back_text, back_text.get_rect(center=self._back_button_rect.center))