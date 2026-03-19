from __future__ import annotations

import math
from typing import List, Optional

import pygame

from animation import SpriteAnimation, load_frames_from_directory
from character_manager import (
    DEFAULT_CHARACTER_NAME,
    available_characters,
    build_animation_paths,
)
from settings import (
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    FONT_SIZE_BODY,
    FONT_SIZE_HEADING,
    MODE_LOCAL_MULTIPLAYER,
    MODE_ONLINE_MULTIPLAYER,
    MODE_VS_COMPUTER,
    SCENE_FADE_SPEED,
    SCENE_OVERLAY_COLOR,
    TARGET_FPS,
    WINDOW_SIZE,
)
from .common import _draw_rounded_rect, _load_font

# Visual constants for the grid and controls
BACKGROUND_COLOR = (8, 12, 24)
PANEL_OVERLAY = (255, 255, 255, 20)
HEADER_COLOR = (255, 255, 255)
SUBHEADER_COLOR = (180, 190, 220)
MODE_HINT_COLOR = (140, 160, 210)
CARD_BG = (24, 32, 56, 235)
CARD_BG_HOVER = (34, 44, 74, 240)
CARD_BG_ACTIVE = (58, 48, 24, 245)
CARD_BG_LOCKED = (52, 36, 18, 245)
CARD_BORDER_IDLE = (255, 215, 120)
CARD_BORDER_HOVER = (255, 240, 175)
CARD_BORDER_ACTIVE = (252, 202, 110)
CARD_BORDER_LOCKED = (255, 198, 120)
CARD_TEXT_COLOR = (255, 255, 255)
LOCKED_BADGE_BG = (255, 255, 255, 25)
LOCKED_BADGE_TEXT = (250, 210, 120)
INSTRUCTION_COLOR = (185, 195, 220)
PREVIEW_COLOR = (150, 210, 255)
CONFIRMED_COLOR = (120, 240, 170)

CARD_WIDTH = 280
CARD_HEIGHT = 180
CARD_RADIUS = 16
CARD_GUTTER = 26
MAX_COLUMNS = 4
SUMMARY_PANEL_HEIGHT = 140

PREVIEW_SCALE = 0.24
PREVIEW_FRAME_DURATION = 1 / 18
PREVIEW_OFFSET_Y = 14
PLACEHOLDER_SIZE = (96, 96)

BUTTON_WIDTH = 240
BUTTON_HEIGHT = 60
BUTTON_RADIUS = 18
BUTTON_BG = (34, 52, 86)
BUTTON_BG_HOVER = (58, 84, 132)
BUTTON_BG_DISABLED = (20, 30, 48)
BUTTON_TEXT = (255, 255, 255)
BUTTON_TEXT_DISABLED = (140, 150, 180)

MODE_HEADERS = {
    MODE_VS_COMPUTER: ("SOLO RUN", ""),
    MODE_LOCAL_MULTIPLAYER: ("LOCAL MULTIPLAYER", ""),
    MODE_ONLINE_MULTIPLAYER: ("ONLINE MATCH", ""),
    "default": ("CHARACTER SELECT", "Preview idle vs. run before locking in."),
}


class PlayerSelectionScreen:
    """Animated character picker with idle/run previews and multi-player flow."""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock,
                 game_mode: str, num_players: int = 1) -> None:
        self.screen = screen
        self.clock = clock
        self.game_mode = game_mode
        self.num_players = max(1, num_players)
        self.width, self.height = WINDOW_SIZE

        self.mode_title, self.mode_hint = MODE_HEADERS.get(
            game_mode,
            MODE_HEADERS["default"],
        )

        self.characters: List[str] = available_characters() or [DEFAULT_CHARACTER_NAME]
        self.cards: List[dict] = []
        self._build_cards()

        # Fonts
        self._font_heading = _load_font(FONT_PATH_HEADING, FONT_SIZE_HEADING, bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, FONT_SIZE_BODY)
        self._font_small = _load_font(FONT_PATH_BODY, 18)

        # Selection state
        self.current_player = 0
        self.selections: List[Optional[str]] = [None] * self.num_players
        self.active_index: Optional[int] = 0 if self.cards else None
        self.hover_index: Optional[int] = None

        # Buttons
        button_y = self.height - 55
        self._lock_button_rect = pygame.Rect(0, 0, BUTTON_WIDTH, BUTTON_HEIGHT)
        self._lock_button_rect.center = (self.width // 2 + 180, button_y)
        self._back_button_rect = pygame.Rect(0, 0, BUTTON_WIDTH - 30, BUTTON_HEIGHT - 6)
        self._back_button_rect.center = (self.width // 2 - 200, button_y)

    # ── card + animation setup ──────────────────────────────────────────

    def _build_cards(self) -> None:
        if not self.characters:
            return
        cols = min(MAX_COLUMNS, max(1, len(self.characters)))
        rows = math.ceil(len(self.characters) / cols)
        grid_width = cols * CARD_WIDTH + (cols - 1) * CARD_GUTTER
        start_x = self.width // 2 - grid_width // 2
        start_y = 150

        for idx, name in enumerate(self.characters):
            row = idx // cols
            col = idx % cols
            rect = pygame.Rect(
                start_x + col * (CARD_WIDTH + CARD_GUTTER),
                start_y + row * (CARD_HEIGHT + CARD_GUTTER),
                CARD_WIDTH,
                CARD_HEIGHT,
            )
            animations = self._load_preview_animations(name)
            self.cards.append({
                "name": name,
                "rect": rect,
                "animations": animations,
                "current_state": "idle",
            })

    def _load_preview_animations(self, character_name: str) -> dict:
        paths = build_animation_paths(character_name)
        idle_path = self._preferred_direction_path(paths, "idle")
        run_path = self._preferred_direction_path(paths, "run")
        animations = {
            "idle": self._create_animation(idle_path, character_name),
            "run": self._create_animation(run_path, character_name),
        }
        return animations

    @staticmethod
    def _preferred_direction_path(paths: dict, state: str):
        state_paths = paths.get(state, {})
        if "down" in state_paths:
            return state_paths["down"]
        return state_paths.get("front") or next(iter(state_paths.values()), None)

    def _create_animation(self, directory, character_name: str) -> SpriteAnimation:
        frames = None
        if directory is not None:
            try:
                frames = load_frames_from_directory(directory, scale=PREVIEW_SCALE)
            except (FileNotFoundError, ValueError, pygame.error):
                frames = None
        if not frames:
            frames = [self._placeholder_surface(character_name)]
        return SpriteAnimation(frames, frame_duration=PREVIEW_FRAME_DURATION, loop=True)

    def _placeholder_surface(self, name: str) -> pygame.Surface:
        surface = pygame.Surface(PLACEHOLDER_SIZE, pygame.SRCALPHA)
        base = 80 + (hash(name) % 90)
        color = (base, 900 + (hash(name[::-1]) % 80), 140 + (hash(name) % 60))
        pygame.draw.circle(surface, color, (PLACEHOLDER_SIZE[0] // 2, PLACEHOLDER_SIZE[1] // 2), PLACEHOLDER_SIZE[0] // 2 - 6)
        pygame.draw.circle(surface, (255, 255, 255, 55), (PLACEHOLDER_SIZE[0] // 2, PLACEHOLDER_SIZE[1] // 2 - 8), 14)
        return surface

    # ── drawing helpers ────────────────────────────────────────────────

    def _draw_background(self) -> None:
        self.screen.fill(BACKGROUND_COLOR)
        overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        overlay.fill(PANEL_OVERLAY)
        self.screen.blit(overlay, (0, 0))

    def _draw_header(self) -> None:
        title_surf = self._font_heading.render(self.mode_title, True, HEADER_COLOR)
        subtitle = f"Selecting player {self.current_player + 1} of {self.num_players}"
        subtitle_surf = self._font_body.render(subtitle, True, SUBHEADER_COLOR)
        hint_surf = self._font_small.render(self.mode_hint, True, MODE_HINT_COLOR)

        self.screen.blit(title_surf, title_surf.get_rect(center=(self.width // 2, 70)))
        self.screen.blit(subtitle_surf, subtitle_surf.get_rect(center=(self.width // 2, 116)))
        self.screen.blit(hint_surf, hint_surf.get_rect(center=(self.width // 2, 148)))

    def _draw_cards(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        self.hover_index = None

        for idx, card in enumerate(self.cards):
            rect = card["rect"]
            hovered = rect.collidepoint(mouse_pos)
            if hovered:
                self.hover_index = idx

            is_active = idx == self.active_index
            locked_slots = self._locked_slots_for(card["name"])

            if locked_slots:
                bg_color = CARD_BG_LOCKED
                border_color = CARD_BORDER_LOCKED
            elif is_active:
                bg_color = CARD_BG_ACTIVE
                border_color = CARD_BORDER_ACTIVE
            elif hovered:
                bg_color = CARD_BG_HOVER
                border_color = CARD_BORDER_HOVER
            else:
                bg_color = CARD_BG
                border_color = CARD_BORDER_IDLE

            _draw_rounded_rect(self.screen, rect, bg_color, border_color, 2, CARD_RADIUS)

            animation = card["animations"][card["current_state"]]
            frame = animation.image
            frame_rect = frame.get_rect(center=(rect.centerx, rect.top + frame.get_height() // 2 + PREVIEW_OFFSET_Y))
            self.screen.blit(frame, frame_rect)

            name_surf = self._font_body.render(card["name"].upper(), True, CARD_TEXT_COLOR)
            name_rect = name_surf.get_rect(midtop=(rect.centerx, rect.bottom - 25))
            self.screen.blit(name_surf, name_rect)

            if locked_slots:
                badge_text = ", ".join(f"P{slot + 1}" for slot in locked_slots)
                badge = self._font_small.render(badge_text, True, LOCKED_BADGE_TEXT)
                badge_bg = pygame.Surface((badge.get_width() + 14, badge.get_height() + 6), pygame.SRCALPHA)
                badge_bg.fill(LOCKED_BADGE_BG)
                badge_pos = (rect.left + 10, rect.top + 10)
                self.screen.blit(badge_bg, badge_pos)
                self.screen.blit(badge, (badge_pos[0] + 7, badge_pos[1] + 3))

    def _draw_summary(self) -> None:
        panel_rect = pygame.Rect(0, self.height - SUMMARY_PANEL_HEIGHT, self.width, SUMMARY_PANEL_HEIGHT)
        panel_surface = pygame.Surface(panel_rect.size, pygame.SRCALPHA)
        panel_surface.fill((12, 16, 26, 238))
        self.screen.blit(panel_surface, panel_rect.topleft)

        if self.num_players == 1:
            instructions = "Click to preview running animation. Press ENTER or LOCK IN to confirm."
        else:
            instructions = "Player {0}: preview with click/arrows, then LOCK IN. BACKSPACE undoes last lock.".format(self.current_player + 1)
        instr_surf = self._font_small.render(instructions, True, INSTRUCTION_COLOR)
        self.screen.blit(instr_surf, instr_surf.get_rect(midtop=(self.width // 2, panel_rect.top + 10)))

        picks = [name or "—" for name in self.selections]
        picks_text = " | ".join(f"P{i + 1}: {choice}" for i, choice in enumerate(picks))
        color = CONFIRMED_COLOR if all(name is not None for name in self.selections[:self.current_player]) else PREVIEW_COLOR
        picks_surf = self._font_body.render(picks_text, True, color)
        self.screen.blit(picks_surf, picks_surf.get_rect(center=(self.width // 2, panel_rect.top + 52)))

        mouse_pos = pygame.mouse.get_pos()
        self._draw_buttons(mouse_pos)

    def _draw_buttons(self, mouse_pos: tuple) -> None:
        # Back button
        back_hover = self._back_button_rect.collidepoint(mouse_pos)
        back_bg = BUTTON_BG_HOVER if back_hover else BUTTON_BG
        _draw_rounded_rect(self.screen, self._back_button_rect, back_bg, CARD_BORDER_IDLE, 2, BUTTON_RADIUS)
        back_text = self._font_body.render("BACK", True, BUTTON_TEXT)
        self.screen.blit(back_text, back_text.get_rect(center=self._back_button_rect.center))

        # Lock button
        lock_enabled = self.active_index is not None and self.current_player < self.num_players
        lock_hover = lock_enabled and self._lock_button_rect.collidepoint(mouse_pos)
        if not lock_enabled:
            lock_bg = BUTTON_BG_DISABLED
            text_color = BUTTON_TEXT_DISABLED
        else:
            lock_bg = BUTTON_BG_HOVER if lock_hover else BUTTON_BG
            text_color = BUTTON_TEXT
        label = "LOCK IN" if self.current_player < self.num_players - 1 else "FINALIZE"
        _draw_rounded_rect(self.screen, self._lock_button_rect, lock_bg, CARD_BORDER_IDLE, 2, BUTTON_RADIUS)
        lock_text = self._font_body.render(label, True, text_color)
        self.screen.blit(lock_text, lock_text.get_rect(center=self._lock_button_rect.center))

    def _draw(self) -> None:
        self._draw_background()
        self._draw_header()
        self._draw_cards()
        self._draw_summary()

    # ── selection helpers ──────────────────────────────────────────────

    def _locked_slots_for(self, character_name: str) -> List[int]:
        return [idx for idx, choice in enumerate(self.selections) if choice == character_name]

    def _move_active(self, delta: int) -> None:
        if not self.cards:
            return
        if self.active_index is None:
            self.active_index = 0
            return
        self.active_index = (self.active_index + delta) % len(self.cards)

    def _move_vertical(self, direction: int) -> None:
        if not self.cards:
            return
        cols = min(MAX_COLUMNS, max(1, len(self.cards)))
        if self.active_index is None:
            self.active_index = 0
            return
        self.active_index = (self.active_index + direction * cols) % len(self.cards)

    def _set_active_index(self, index: int) -> None:
        if 0 <= index < len(self.cards):
            self.active_index = index

    def _lock_current_selection(self) -> Optional[List[str]]:
        if self.active_index is None or self.current_player >= self.num_players:
            return None
        choice = self.cards[self.active_index]["name"]
        self.selections[self.current_player] = choice
        self.current_player += 1

        if self.current_player >= self.num_players:
            selections = [name or self.characters[0] for name in self.selections]
            self._fade(False)
            return selections

        # Keep the same active card so the next player can see it running
        return None

    def _undo_selection(self) -> None:
        if self.current_player == 0:
            self.selections[0] = None
            return
        self.current_player -= 1
        previous = self.selections[self.current_player]
        self.selections[self.current_player] = None
        if previous and previous in self.characters:
            self.active_index = self.characters.index(previous)

    def _update_card_states(self, dt: float) -> None:
        for idx, card in enumerate(self.cards):
            desired_state = "run" if idx == self.active_index else "idle"
            if card["current_state"] != desired_state:
                card["current_state"] = desired_state
                card["animations"][desired_state].reset()
            card["animations"][card["current_state"]].update(dt)

    # ── fade utility ───────────────────────────────────────────────────

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

            self._update_card_states(dt)
            self._draw()
            overlay.set_alpha(int(alpha))
            overlay.fill(SCENE_OVERLAY_COLOR)
            self.screen.blit(overlay, (0, 0))
            pygame.display.flip()

    # ── main loop ───────────────────────────────────────────────────────

    def run(self) -> List[str] | None:
        if not self.cards:
            return None

        self._fade(True)

        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._update_card_states(dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._lock_button_rect.collidepoint(event.pos):
                        result = self._lock_current_selection()
                        if result is not None:
                            return result
                    elif self._back_button_rect.collidepoint(event.pos):
                        return None
                    else:
                        for idx, card in enumerate(self.cards):
                            if card["rect"].collidepoint(event.pos):
                                self._set_active_index(idx)
                                break
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return None
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        result = self._lock_current_selection()
                        if result is not None:
                            return result
                    elif event.key in (pygame.K_LEFT, pygame.K_a):
                        self._move_active(-1)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        self._move_active(1)
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        self._move_vertical(-1)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        self._move_vertical(1)
                    elif event.key == pygame.K_BACKSPACE:
                        self._undo_selection()
                    elif pygame.K_1 <= event.key <= pygame.K_9:
                        idx = min(len(self.cards) - 1, event.key - pygame.K_1)
                        self._set_active_index(idx)

            self._draw()
            pygame.display.flip()


__all__ = ["PlayerSelectionScreen"]
