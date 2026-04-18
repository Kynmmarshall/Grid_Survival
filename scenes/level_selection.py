from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pygame

from settings import (
    ASSETS_DIR,
    BACKGROUND_PATH,
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    FONT_PATH_SMALL,
    FONT_SIZE_BODY,
    FONT_SIZE_HEADING,
    FONT_SIZE_SMALL,
    MAP_PATH,
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


@dataclass(frozen=True)
class LevelOption:
    level_id: int
    name: str
    map_path: Path
    background_path: Path


def _parse_level_number(path: Path) -> int | None:
    stem = path.stem.lower()
    if not stem.startswith("level_"):
        return None
    suffix = stem[len("level_"):]
    if not suffix.isdigit():
        return None
    return int(suffix)


def _collect_level_files(directory: Path, suffixes: set[str]) -> dict[int, Path]:
    collected: dict[int, Path] = {}
    if not directory.exists():
        return collected

    for path in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        number = _parse_level_number(path)
        if number is None:
            continue
        collected[number] = path

    return collected


def discover_level_options() -> list[LevelOption]:
    maps_dir = ASSETS_DIR / "maps"
    backgrounds_dir = ASSETS_DIR / "Background"

    maps = _collect_level_files(maps_dir, {".tmx"})
    backgrounds = _collect_level_files(backgrounds_dir, {".png", ".jpg", ".jpeg", ".webp"})

    level_ids = sorted(set(maps).intersection(backgrounds))
    options = [
        LevelOption(
            level_id=level_id,
            name=f"LEVEL {level_id}",
            map_path=maps[level_id],
            background_path=backgrounds[level_id],
        )
        for level_id in level_ids
    ]

    if options:
        return options

    # Fallback to global defaults if numbered assets are missing.
    return [
        LevelOption(
            level_id=1,
            name="LEVEL 1",
            map_path=MAP_PATH,
            background_path=BACKGROUND_PATH,
        )
    ]


def resolve_level_option(level_id: int, levels: list[LevelOption] | None = None) -> LevelOption | None:
    options = levels if levels is not None else discover_level_options()
    for option in options:
        if option.level_id == level_id:
            return option
    return options[0] if options else None


class LevelSelectionScreen:
    """Select a level/map before character selection."""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock, game_mode: str):
        self.screen = screen
        self.clock = clock
        self.game_mode = game_mode
        self.width, self.height = WINDOW_SIZE
        self.quit_requested = False
        self._audio_overlay = SceneAudioOverlay()

        self.levels = discover_level_options()

        self._font_header = _load_font(FONT_PATH_HEADING, max(28, FONT_SIZE_HEADING + 4), bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, FONT_SIZE_BODY)
        self._font_small = _load_font(FONT_PATH_SMALL, FONT_SIZE_SMALL)

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

        self._preview_cache: dict[int, pygame.Surface] = {}
        self._cards = self._build_cards()

    def _build_cards(self) -> list[dict]:
        card_w = 180
        card_h = 154
        gap_x = 24
        gap_y = 26

        cols = max(1, min(5, self.width // (card_w + gap_x)))
        rows = max(1, math.ceil(len(self.levels) / cols))

        total_w = cols * card_w + (cols - 1) * gap_x
        top_margin = 170
        bottom_margin = 120
        available_h = max(1, self.height - top_margin - bottom_margin)
        total_h = rows * card_h + (rows - 1) * gap_y

        start_x = (self.width - total_w) // 2
        start_y = top_margin + max(0, (available_h - total_h) // 2)

        cards: list[dict] = []
        for idx, level in enumerate(self.levels):
            row = idx // cols
            col = idx % cols
            rect = pygame.Rect(
                start_x + col * (card_w + gap_x),
                start_y + row * (card_h + gap_y),
                card_w,
                card_h,
            )
            cards.append({"index": idx, "rect": rect, "level": level, "cols": cols})

        return cards

    def _preview_for(self, level: LevelOption, target_size: tuple[int, int]) -> pygame.Surface:
        cached = self._preview_cache.get(level.level_id)
        if cached is not None and cached.get_size() == target_size:
            return cached

        surf = pygame.Surface(target_size)
        surf.fill((15, 20, 32))

        if level.background_path.exists():
            try:
                image = pygame.image.load(str(level.background_path)).convert()
                img_w, img_h = image.get_size()
                scale = max(target_size[0] / img_w, target_size[1] / img_h)
                new_w = max(1, int(img_w * scale))
                new_h = max(1, int(img_h * scale))
                scaled = pygame.transform.smoothscale(image, (new_w, new_h))
                crop_x = max(0, (new_w - target_size[0]) // 2)
                crop_y = max(0, (new_h - target_size[1]) // 2)
                surf.blit(scaled, (-crop_x, -crop_y))
            except Exception:
                pass

        shade = pygame.Surface(target_size, pygame.SRCALPHA)
        shade.fill((4, 8, 14, 55))
        surf.blit(shade, (0, 0))

        self._preview_cache[level.level_id] = surf
        return surf

    def _draw_background(self) -> None:
        if self._bg_image:
            self.screen.blit(self._bg_image, (0, 0))
            overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 125))
            self.screen.blit(overlay, (0, 0))
        else:
            self.screen.fill(MODE_BG_COLOR)

    def _draw_header(self) -> None:
        title = self._font_header.render("SELECT LEVEL", True, (255, 255, 255))
        subtitle = self._font_body.render("Choose an arena before selecting your character", True, (205, 215, 235))

        self.screen.blit(title, title.get_rect(center=(self.width // 2, 78)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(self.width // 2, 126)))

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
            level = card["level"]
            rect = card["rect"].copy()

            hovered = rect.collidepoint(mouse_pos)
            selected = idx == self._selected_index
            if hovered:
                self._hover_index = idx

            if hovered:
                rect.y -= 3

            if selected:
                pulse = 0.5 + 0.5 * math.sin(self._anim_time * 6.0)
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

            image_rect = pygame.Rect(rect.left + 8, rect.top + 8, rect.width - 16, rect.height - 44)
            preview = self._preview_for(level, image_rect.size)
            self.screen.blit(preview, image_rect.topleft)
            pygame.draw.rect(self.screen, (20, 24, 36), image_rect, 1, border_radius=8)

            label = self._font_small.render(level.name, True, (230, 235, 245))
            label_rect = label.get_rect(center=(rect.centerx, rect.bottom - 18))
            self.screen.blit(label, label_rect)

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

    def run(self) -> LevelOption | None:
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
                        return self.levels[self._selected_index]
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
                            return self.levels[self._selected_index]

            if self._hover_index is not None:
                self._selected_index = self._hover_index

            self._draw()
            pygame.display.flip()


__all__ = [
    "LevelOption",
    "discover_level_options",
    "resolve_level_option",
    "LevelSelectionScreen",
]
