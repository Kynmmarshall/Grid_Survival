"""
Opening scenes for Grid Survival.
TitleScreen and ModeSelectionScreen with polished fonts, animations, and UI.
"""

import math
import random

import pygame

from animation import SpriteAnimation, load_frames_from_directory
from audio import get_audio
from character_manager import (
    DEFAULT_CHARACTER_NAME,
    available_characters,
    build_animation_paths,
)
from settings import (
    # Audio
    MUSIC_PATH,
    MUSIC_VOLUME,
    # Window
    WINDOW_SIZE,
    TARGET_FPS,
    # Fade
    SCENE_FADE_SPEED,
    SCENE_OVERLAY_COLOR,
    # Title screen
    TITLE_TEXT,
    TITLE_BG_COLOR,
    TITLE_COLORS,
    TITLE_DROP_DURATION,
    TITLE_PULSE_SPEED,
    TITLE_PARTICLE_COUNT,
    TITLE_PARTICLE_MIN_SIZE,
    TITLE_PARTICLE_MAX_SIZE,
    TITLE_PARTICLE_MIN_SPEED,
    TITLE_PARTICLE_MAX_SPEED,
    TITLE_PARTICLE_COLOR_BASE,
    TITLE_SUBTITLE_COLOR,
    TITLE_SHAKE_INTERVAL,
    TITLE_SHAKE_OFFSET,
    TITLE_SHAKE_FRAMES,
    SUBTITLE_FLOAT_AMPLITUDE,
    SUBTITLE_FLOAT_SPEED,
    # Input box
    NAME_MAX_LENGTH,
    INPUT_BOX_WIDTH,
    INPUT_BOX_HEIGHT,
    INPUT_BOX_BG_COLOR,
    INPUT_BOX_BORDER_COLOR,
    INPUT_BOX_BORDER_UNFOCUSED,
    INPUT_LABEL_COLOR,
    INPUT_TEXT_COLOR,
    PROMPT_TEXT_COLOR,
    PROMPT_BLINK_SPEED,
    WARNING_TEXT_COLOR,
    WARNING_DISPLAY_DURATION,
    CURSOR_BLINK_SPEED,
    # Mode selection
    MODE_BG_COLOR,
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
    # Game modes
    MODE_VS_COMPUTER,
    MODE_LOCAL_MULTIPLAYER,
    MODE_ONLINE_MULTIPLAYER,
    # Font hierarchy
    FONT_PATH_DISPLAY,
    FONT_PATH_HEADING,
    FONT_PATH_BODY,
    FONT_PATH_SMALL,
    FONT_SIZE_DISPLAY,
    FONT_SIZE_HEADING,
    FONT_SIZE_BODY,
    FONT_SIZE_SMALL,
    # Player previews
    PLAYER_FRAME_DURATION,
    PLAYER_SCALE,
)


# ─────────────────────────────────────────────────────────────────────────────
# Font loader helper
# ─────────────────────────────────────────────────────────────────────────────

def _load_font(path: str, size: int, bold: bool = False) -> pygame.font.Font:
    """Try to load a TTF font; fall back to Consolas system font."""
    try:
        return pygame.font.Font(path, size)
    except (pygame.error, FileNotFoundError, OSError):
        try:
            return pygame.font.SysFont("consolas", size, bold=bold)
        except Exception:
            return pygame.font.Font(None, size)


# ─────────────────────────────────────────────────────────────────────────────
# Rounded-rect panel helper (shared with ui.py logic)
# ─────────────────────────────────────────────────────────────────────────────

def _draw_rounded_rect(surface: pygame.Surface, rect: pygame.Rect,
                       color: tuple, border_color: tuple,
                       border_width: int = 2, radius: int = 12):
    bg = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(bg, color, bg.get_rect(), border_radius=radius)
    surface.blit(bg, rect.topleft)
    pygame.draw.rect(surface, border_color, rect, border_width, border_radius=radius)


# ─────────────────────────────────────────────────────────────────────────────
# TitleScreen
# ─────────────────────────────────────────────────────────────────────────────

class TitleScreen:
    """Opening title screen with animated logo, particles, and name entry."""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        self.screen = screen
        self.clock = clock
        self.width, self.height = WINDOW_SIZE
        self.audio = get_audio()

        # Font hierarchy
        self._font_display = _load_font(FONT_PATH_DISPLAY, FONT_SIZE_DISPLAY, bold=True)
        self._font_heading = _load_font(FONT_PATH_HEADING, FONT_SIZE_HEADING)
        self._font_body = _load_font(FONT_PATH_BODY, FONT_SIZE_BODY)
        self._font_small = _load_font(FONT_PATH_SMALL, FONT_SIZE_SMALL)

        self.player_name = ""
        self.warning_text = ""
        self.warning_timer = 0.0
        self._title_time = 0.0

        # Title letter animation
        self._letters = []
        self._build_title_letters()

        # Subtitle fade-in state
        self._subtitle_visible = False
        self._subtitle_alpha = 0.0
        self._subtitle_float_offset = 0.0

        # Title shake state
        self._shake_timer = 0.0
        self._shake_offset_x = 0
        self._shaking = False
        self._shake_frame = 0

        # Cursor blink
        self._cursor_timer = 0.0
        self._cursor_visible = True

        # Particles
        self._particles = []
        self._spawn_particles(TITLE_PARTICLE_COUNT)

        self._start_music()

    # ── music ──────────────────────────────────────────────────────────────

    def _start_music(self) -> None:
        self.audio.play_music(
            track=MUSIC_PATH,
            loop=True,
            fade_ms=1500,
            volume=MUSIC_VOLUME,
        )

    # ── title letter setup ─────────────────────────────────────────────────

    def _build_title_letters(self) -> None:
        # Measure total width using the display font
        test_surf = self._font_display.render(TITLE_TEXT, True, (255, 255, 255))
        total_w = test_surf.get_width()
        start_x = self.width // 2 - total_w // 2
        base_y = 140

        # Render each character individually to get per-char widths
        x_cursor = start_x
        for idx, ch in enumerate(TITLE_TEXT):
            ch_surf = self._font_display.render(ch, True, (255, 255, 255))
            ch_w = ch_surf.get_width()
            if ch != " ":
                self._letters.append({
                    "char": ch,
                    "x": x_cursor + ch_w // 2,
                    "base_y": base_y,
                    "start_delay": idx * 0.06,
                    "landed": False,
                })
            x_cursor += ch_w

    # ── particles ──────────────────────────────────────────────────────────

    def _spawn_particles(self, count: int) -> None:
        for _ in range(count):
            self._particles.append({
                "x": random.uniform(80, self.width - 80),
                "y": random.uniform(180, self.height - 120),
                "size": random.randint(TITLE_PARTICLE_MIN_SIZE, TITLE_PARTICLE_MAX_SIZE),
                "speed": random.uniform(TITLE_PARTICLE_MIN_SPEED, TITLE_PARTICLE_MAX_SPEED),
                "phase": random.uniform(0, math.pi * 2),
            })

    def _update_particles(self, dt: float) -> None:
        for p in self._particles:
            p["y"] -= p["speed"] * dt
            p["x"] += math.sin(self._title_time * 2.0 + p["phase"]) * 18 * dt
            if p["y"] < 120:
                p["y"] = self.height - 80
                p["x"] = random.uniform(80, self.width - 80)

    # ── drawing ────────────────────────────────────────────────────────────

    def _draw_background(self) -> None:
        self.screen.fill(TITLE_BG_COLOR)
        for p in self._particles:
            alpha = int(80 + 60 * math.sin(self._title_time * 4 + p["phase"]))
            color = (
                TITLE_PARTICLE_COLOR_BASE[0],
                TITLE_PARTICLE_COLOR_BASE[1],
                TITLE_PARTICLE_COLOR_BASE[2],
                max(20, min(180, alpha)),
            )
            tile_surf = pygame.Surface((p["size"], p["size"]), pygame.SRCALPHA)
            pygame.draw.rect(tile_surf, color, tile_surf.get_rect(), border_radius=2)
            self.screen.blit(tile_surf, (p["x"], p["y"]))

    def _draw_title(self) -> None:
        # Pulse scale
        pulse = 1.0 + 0.06 * math.sin(self._title_time * TITLE_PULSE_SPEED)
        color_index = int(self._title_time * 2.5) % len(TITLE_COLORS)
        base_color = TITLE_COLORS[color_index]

        # Shake offset
        shake_x = self._shake_offset_x

        all_landed = True
        for idx, info in enumerate(self._letters):
            t = max(0.0, self._title_time - info["start_delay"])
            drop_progress = min(1.0, t / TITLE_DROP_DURATION)
            ease = 1 - (1 - drop_progress) ** 3
            y = -80 + (info["base_y"] + 80) * ease
            bounce = 7 * math.sin(self._title_time * 9 + idx) * (1.0 - drop_progress)

            if drop_progress < 1.0:
                all_landed = False

            color = (
                min(255, base_color[0] + idx * 3),
                max(0, base_color[1] - idx * 2),
                base_color[2],
            )

            surf = self._font_display.render(info["char"], True, color)
            w, h = surf.get_size()
            surf = pygame.transform.smoothscale(
                surf,
                (max(1, int(w * pulse)), max(1, int(h * pulse))),
            )
            rect = surf.get_rect(center=(info["x"] + shake_x, y + bounce))
            self.screen.blit(surf, rect)

        # Subtitle: fade in after all letters land
        if all_landed:
            self._subtitle_alpha = min(255.0, self._subtitle_alpha + 180 * (1 / 60))
        subtitle_text = "SURVIVE THE FALLING TILES"
        subtitle_surf = self._font_heading.render(subtitle_text, True, TITLE_SUBTITLE_COLOR)
        subtitle_surf.set_alpha(int(self._subtitle_alpha))
        float_y = math.sin(self._title_time * SUBTITLE_FLOAT_SPEED * math.pi * 2) * SUBTITLE_FLOAT_AMPLITUDE
        subtitle_rect = subtitle_surf.get_rect(center=(self.width // 2, 220 + float_y))
        self.screen.blit(subtitle_surf, subtitle_rect)

    def _draw_input(self) -> None:
        # Label
        label = self._font_small.render("ENTER YOUR NAME :", True, INPUT_LABEL_COLOR)
        self.screen.blit(label, label.get_rect(center=(self.width // 2, 310)))

        # Input box
        box_rect = pygame.Rect(0, 0, INPUT_BOX_WIDTH, INPUT_BOX_HEIGHT)
        box_rect.center = (self.width // 2, 370)
        border_color = INPUT_BOX_BORDER_COLOR  # always gold (focused)
        _draw_rounded_rect(self.screen, box_rect,
                           (*INPUT_BOX_BG_COLOR, 255), border_color, 2, 10)

        # Typed text + blinking cursor
        display_text = self.player_name
        cursor_str = "|" if self._cursor_visible else " "
        text_with_cursor = display_text + cursor_str
        name_surf = self._font_body.render(text_with_cursor, True, INPUT_TEXT_COLOR)
        self.screen.blit(name_surf, name_surf.get_rect(midleft=(box_rect.left + 14, box_rect.centery)))

        # "PRESS ENTER TO CONTINUE" prompt — blinking fade
        prompt_alpha = int(80 + 175 * abs(math.sin(self._title_time * PROMPT_BLINK_SPEED * math.pi)))
        prompt_surf = self._font_small.render("PRESS ENTER TO CONTINUE", True, PROMPT_TEXT_COLOR)
        prompt_surf.set_alpha(prompt_alpha)
        self.screen.blit(prompt_surf, prompt_surf.get_rect(center=(self.width // 2, 440)))

        # Warning message
        if self.warning_text and self.warning_timer > 0:
            warn_alpha = min(255, int(255 * min(1.0, self.warning_timer / 0.3)))
            warn_surf = self._font_small.render(f"⚠ {self.warning_text}", True, WARNING_TEXT_COLOR)
            warn_surf.set_alpha(warn_alpha)
            self.screen.blit(warn_surf, warn_surf.get_rect(center=(self.width // 2, 490)))

    # ── shake update ───────────────────────────────────────────────────────

    def _update_shake(self, dt: float) -> None:
        self._shake_timer += dt
        if self._shake_timer >= TITLE_SHAKE_INTERVAL and not self._shaking:
            self._shaking = True
            self._shake_frame = 0
            self._shake_timer = 0.0

        if self._shaking:
            offsets = [TITLE_SHAKE_OFFSET, -TITLE_SHAKE_OFFSET, TITLE_SHAKE_OFFSET, 0]
            frame_idx = min(self._shake_frame, len(offsets) - 1)
            self._shake_offset_x = offsets[frame_idx]
            self._shake_frame += 1
            if self._shake_frame >= len(offsets):
                self._shaking = False
                self._shake_offset_x = 0

    # ── fade ───────────────────────────────────────────────────────────────

    def _fade(self, direction: str) -> None:
        overlay = pygame.Surface(WINDOW_SIZE)
        alpha = 255 if direction == "in" else 0
        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            step = SCENE_FADE_SPEED * dt
            if direction == "in":
                alpha -= step
                if alpha <= 0:
                    break
            else:
                alpha += step
                if alpha >= 255:
                    alpha = 255
                    break

            self._draw_background()
            self._draw_title()
            self._draw_input()
            overlay.set_alpha(int(alpha))
            overlay.fill(SCENE_OVERLAY_COLOR)
            self.screen.blit(overlay, (0, 0))
            pygame.display.flip()

    # ── main loop ──────────────────────────────────────────────────────────

    def run(self):
        self._fade("in")

        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._title_time += dt
            self.warning_timer = max(0.0, self.warning_timer - dt)

            # Cursor blink
            self._cursor_timer += dt
            if self._cursor_timer >= 1.0 / CURSOR_BLINK_SPEED:
                self._cursor_timer = 0.0
                self._cursor_visible = not self._cursor_visible

            # Shake update (every TITLE_SHAKE_INTERVAL seconds)
            self._update_shake(dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        if self.player_name.strip():
                            self._fade("out")
                            return self.player_name.strip()
                        self.warning_text = "PLEASE ENTER YOUR NAME"
                        self.warning_timer = WARNING_DISPLAY_DURATION
                    elif event.key == pygame.K_BACKSPACE:
                        self.player_name = self.player_name[:-1]
                    elif event.unicode and event.unicode.isprintable():
                        if len(self.player_name) < NAME_MAX_LENGTH:
                            self.player_name += event.unicode

            self._update_particles(dt)
            self._draw_background()
            self._draw_title()
            self._draw_input()
            pygame.display.flip()


# ─────────────────────────────────────────────────────────────────────────────
# ModeSelectionScreen
# ─────────────────────────────────────────────────────────────────────────────

class ModeSelectionScreen:
    """Mode select screen shown after successful name entry."""

    # Mode icons (emoji fallback if no sprite)
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

        # Font hierarchy
        self._font_heading = _load_font(FONT_PATH_HEADING, FONT_SIZE_HEADING, bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, FONT_SIZE_BODY)
        self._font_small = _load_font(FONT_PATH_SMALL, FONT_SIZE_SMALL)
        # Card-specific fonts per spec: title 68px, desc 56px
        self._font_card_title = _load_font(FONT_PATH_HEADING, 22, bold=True)   # scaled for readability
        self._font_card_desc = _load_font(FONT_PATH_BODY, 16)
        self._font_header = _load_font(FONT_PATH_HEADING, 36, bold=True)
        # Icon font: 88px centered (emoji)
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
        start_y = (self.height - total_h) // 2 + 60  # leave room for header

        self.cards = [
            {
                "mode": MODE_VS_COMPUTER,
                "title": "VS COMPUTER",
                "desc": "Face an AI-controlled opponent",
                "key": "[1]",
                "rect": pygame.Rect(0, start_y + (card_h + gap) * 0, card_w, card_h),
                "hover_y": 0.0,   # smooth hover offset
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
                "title": "ONLINE MULTIPLAYER",
                "desc": "Play with another player over LAN/Internet",
                "key": "[3]",
                "rect": pygame.Rect(0, start_y + (card_h + gap) * 2, card_w, card_h),
                "hover_y": 0.0,
                "click_scale": 1.0,
                "click_timer": 0.0,
            },
        ]
        # Center cards horizontally
        for card in self.cards:
            card["rect"].centerx = self.width // 2

        self._clicked_mode = None
        self._flash_timer = 0.0

    # ── update ─────────────────────────────────────────────────────────────

    def _update_animations(self, dt: float):
        self._anim_time += dt

        # Header slide-in
        progress = min(1.0, self._anim_time / MODE_HEADER_SLIDE_DURATION)
        ease = 1 - (1 - progress) ** 3
        self._header_y_offset = MODE_HEADER_SLIDE_DISTANCE * (1.0 - ease)
        self._header_alpha = min(255.0, 255 * ease)

        # Subtitle appears after delay
        if self._anim_time >= MODE_HEADER_SLIDE_DURATION + MODE_SUBTITLE_DELAY:
            sub_progress = min(1.0, (self._anim_time - MODE_HEADER_SLIDE_DURATION - MODE_SUBTITLE_DELAY) / 0.5)
            self._subtitle_alpha = min(255.0, 255 * sub_progress)

        # Card hover smooth interpolation
        mouse_pos = pygame.mouse.get_pos()
        for card in self.cards:
            hovered = card["rect"].collidepoint(mouse_pos)
            target_y = -4.0 if hovered else 0.0
            card["hover_y"] += (target_y - card["hover_y"]) * min(1.0, dt * 12)

            # Click scale animation
            if card["click_timer"] > 0:
                card["click_timer"] -= dt
                t = max(0.0, card["click_timer"] / 0.1)
                card["click_scale"] = 1.0 - 0.05 * t
            else:
                card["click_scale"] = 1.0

    # ── drawing ────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        self.screen.fill(MODE_BG_COLOR)

        # Header: "Welcome, [PlayerName]!"
        header_y = int(80 + self._header_y_offset)
        # Render "Welcome, " in white and player name in gold
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

        # Subtitle
        subtitle_surf = self._font_body.render("CHOOSE YOUR GAME MODE", True, MODE_SUBTITLE_COLOR)
        subtitle_surf.set_alpha(int(self._subtitle_alpha))
        self.screen.blit(subtitle_surf, subtitle_surf.get_rect(center=(self.width // 2, header_y + 55)))

        # Cards
        mouse_pos = pygame.mouse.get_pos()
        for card in self.cards:
            self._draw_card(card, mouse_pos)

    def _draw_card(self, card: dict, mouse_pos: tuple) -> None:
        rect = card["rect"].copy()
        rect.y += int(card["hover_y"])

        hovered = rect.collidepoint(mouse_pos)
        selected = self._clicked_mode == card["mode"]
        mode = card["mode"]

        # Background color
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

        # Border color
        if hovered or selected:
            border_color = self._MODE_HOVER_BORDER[mode]
            border_w = 3
        else:
            border_color = self._MODE_BORDER[mode]
            border_w = 2

        # Apply click scale
        if card["click_scale"] != 1.0:
            s = card["click_scale"]
            new_w = int(rect.width * s)
            new_h = int(rect.height * s)
            rect = pygame.Rect(
                rect.centerx - new_w // 2,
                rect.centery - new_h // 2,
                new_w, new_h
            )

        # Draw card background
        _draw_rounded_rect(self.screen, rect, bg_color, border_color, border_w, 16)

        # Flash white on click
        if selected:
            flash_pulse = 0.5 + 0.5 * math.sin(self._flash_timer * 30)
            if flash_pulse > 0.8:
                flash_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
                pygame.draw.rect(flash_surf, (255, 255, 255, 40), flash_surf.get_rect(), border_radius=16)
                self.screen.blit(flash_surf, rect.topleft)

        # Icon row
        icon_str = self._MODE_ICONS.get(card["mode"], "?")
        try:
            icon_surf = self._font_icon.render(icon_str, True, (255, 255, 255))
        except Exception:
            icon_surf = self._font_body.render(icon_str, True, (255, 255, 255))
        icon_rect = icon_surf.get_rect(centerx=rect.centerx, top=rect.top + 18)
        self.screen.blit(icon_surf, icon_rect)

        # Title row
        title_color = border_color if hovered else MODE_CARD_TITLE_COLOR
        title_surf = self._font_card_title.render(card["title"], True, title_color)
        title_rect = title_surf.get_rect(centerx=rect.centerx, top=icon_rect.bottom + 10)
        self.screen.blit(title_surf, title_rect)

        # Description row
        desc_surf = self._font_card_desc.render(card["desc"], True, MODE_CARD_DESC_COLOR)
        desc_rect = desc_surf.get_rect(centerx=rect.centerx, top=title_rect.bottom + 8)
        self.screen.blit(desc_surf, desc_rect)

        # Key hint (small, bottom-right of card)
        key_surf = self._font_small.render(card["key"], True, border_color)
        key_rect = key_surf.get_rect(right=rect.right - 12, bottom=rect.bottom - 10)
        self.screen.blit(key_surf, key_rect)

    # ── fade ───────────────────────────────────────────────────────────────

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

    # ── main loop ──────────────────────────────────────────────────────────

    def run(self):
        self._fade(True)

        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._flash_timer += dt
            self._update_animations(dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
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
                # Brief click flash
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


# ─────────────────────────────────────────────────────────────────────────────
# PlayerSelectionScreen
# ─────────────────────────────────────────────────────────────────────────────


class PlayerSelectionScreen:
    """Allow one or more players to choose their character previews."""

    CARD_WIDTH = 190
    CARD_HEIGHT = 250
    CARD_SPACING_X = 36
    CARD_SPACING_Y = 30
    BACKGROUND_COLOR = (12, 14, 26)
    CARD_BG = (34, 38, 52)
    CARD_BORDER = (70, 80, 110)
    CARD_ACTIVE_BORDER = (110, 200, 255)
    PLAYER_COLORS = [
        (255, 220, 120),
        (130, 210, 255),
        (255, 150, 210),
        (150, 255, 190),
    ]
    BUTTON_SIZE = (260, 62)
    BUTTON_IDLE = (90, 150, 255)
    BUTTON_DISABLED = (70, 70, 90)

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock,
                 game_mode: str, num_players: int = 1):
        self.screen = screen
        self.clock = clock
        self.width, self.height = WINDOW_SIZE
        self.game_mode = game_mode
        self.num_players = max(1, num_players)
        self.characters = available_characters() or [DEFAULT_CHARACTER_NAME]
        self.previews = self._load_previews()
        self.card_rects: list[pygame.Rect] = []
        self.selection: list[int | None] = [None] * self.num_players
        self.locked_in = [False] * self.num_players
        self.current_player = 0
        self.active_card_idx: int | None = None
        self.done = False
        self.cancelled = False

        self.font_title = _load_font(FONT_PATH_HEADING, 34, bold=True)
        self.font_body = _load_font(FONT_PATH_BODY, 20)
        self.font_small = _load_font(FONT_PATH_SMALL, 18)

        self.button_rect = pygame.Rect(0, 0, *self.BUTTON_SIZE)
        self.button_rect.centerx = self.width // 2
        self.button_rect.bottom = self.height - 28
        self.mode_label = self._mode_label()

    # ── lifecycle ──────────────────────────────────────────────────────────

    def run(self):
        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.cancelled = True
                    self.done = True
                else:
                    self._handle_event(event)

            if self.done:
                break

            self._update_animations(dt)
            self._draw()
            pygame.display.flip()

        if self.cancelled:
            return None
        return self._build_result()

    # ── setup helpers ─────────────────────────────────────────────────────

    def _mode_label(self) -> str:
        if self.game_mode == MODE_LOCAL_MULTIPLAYER:
            return "Local Multiplayer"
        if self.game_mode == MODE_VS_COMPUTER:
            return "Single Player"
        if self.game_mode == MODE_ONLINE_MULTIPLAYER:
            return "Online Multiplayer"
        return "Custom Mode"

    def _load_previews(self):
        previews = []
        for name in self.characters:
            paths = build_animation_paths(name)
            front_idle = paths.get("idle", {}).get("down")
            front_run = paths.get("run", {}).get("down")
            previews.append({
                "name": name,
                "animations": {
                    "idle": self._create_animation(front_idle),
                    "run": self._create_animation(front_run),
                },
            })
        return previews

    def _create_animation(self, directory):
        frames = []
        if directory is not None:
            try:
                frames = load_frames_from_directory(directory, scale=PLAYER_SCALE)
            except (FileNotFoundError, ValueError, pygame.error):
                frames = []
        if not frames:
            placeholder = pygame.Surface((96, 96), pygame.SRCALPHA)
            placeholder.fill((0, 0, 0, 0))
            pygame.draw.rect(placeholder, (200, 200, 208), placeholder.get_rect(), border_radius=18)
            frames = [placeholder]
        return SpriteAnimation(frames, frame_duration=PLAYER_FRAME_DURATION, loop=True)

    # ── event handling ─────────────────────────────────────────────────────

    def _handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.cancelled = True
                self.done = True
                return
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._confirm_selection()
            elif event.key in (pygame.K_LEFT, pygame.K_a):
                self._move_selection(-1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self._move_selection(1)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.button_rect.collidepoint(event.pos):
                self._confirm_selection()
                return
            for idx, rect in enumerate(self.card_rects):
                if rect.collidepoint(event.pos):
                    self._activate_card(idx)
                    break

    def _move_selection(self, delta: int):
        if not self._can_interact():
            return
        if not self.characters:
            return
        base_idx = self.active_card_idx
        if base_idx is None:
            choice = self.selection[self.current_player]
            base_idx = choice if choice is not None else 0
        new_idx = (base_idx + delta) % len(self.characters)
        self._activate_card(new_idx)

    def _activate_card(self, idx: int):
        if not self._can_interact():
            return
        if not (0 <= idx < len(self.characters)):
            return
        if idx != self.active_card_idx:
            run_anim = self.previews[idx]["animations"].get("run")
            if run_anim:
                run_anim.reset()
        self.active_card_idx = idx
        self.selection[self.current_player] = idx

    def _confirm_selection(self):
        if not self._can_lock_current_player():
            return
        choice = self.selection[self.current_player]
        if choice is None:
            return
        self.locked_in[self.current_player] = True
        self.active_card_idx = None
        self.current_player += 1
        if self.current_player >= self.num_players:
            self.done = True

    def _can_interact(self) -> bool:
        return not self.done and self.current_player < self.num_players

    def _can_lock_current_player(self) -> bool:
        if not self._can_interact():
            return False
        return self.selection[self.current_player] is not None

    # ── drawing ────────────────────────────────────────────────────────────

    def _draw(self):
        self.screen.fill(self.BACKGROUND_COLOR)
        self._draw_header()
        self._draw_cards()
        self._draw_button()
        self._draw_tips()

    def _draw_header(self):
        title = "CHOOSE YOUR SURVIVOR" if self.num_players == 1 else "ASSEMBLE YOUR CREW"
        title_surf = self.font_title.render(title, True, (255, 220, 120))
        self.screen.blit(title_surf, title_surf.get_rect(center=(self.width // 2, 70)))

        mode_surf = self.font_body.render(self.mode_label.upper(), True, (180, 180, 190))
        self.screen.blit(mode_surf, mode_surf.get_rect(center=(self.width // 2, 110)))

        if not self.done:
            prompt = f"Player {self.current_player + 1}: Click a character to preview their run"
        else:
            prompt = "All players locked in!"
        prompt_color = (200, 200, 210) if not self.done else (130, 215, 150)
        prompt_surf = self.font_small.render(prompt, True, prompt_color)
        self.screen.blit(prompt_surf, prompt_surf.get_rect(center=(self.width // 2, 138)))

    def _draw_cards(self):
        total = len(self.previews)
        if total == 0:
            self.card_rects = []
            return
        cards_per_row = min(4, max(1, total))
        rows = math.ceil(total / cards_per_row)
        total_width = cards_per_row * self.CARD_WIDTH + (cards_per_row - 1) * self.CARD_SPACING_X
        start_x = self.width // 2 - total_width // 2
        grid_top = 170
        self.card_rects = [pygame.Rect(0, 0, 0, 0)] * total

        for idx, preview in enumerate(self.previews):
            row = idx // cards_per_row
            col = idx % cards_per_row
            x = start_x + col * (self.CARD_WIDTH + self.CARD_SPACING_X)
            y = grid_top + row * (self.CARD_HEIGHT + self.CARD_SPACING_Y)
            rect = pygame.Rect(x, y, self.CARD_WIDTH, self.CARD_HEIGHT)
            self.card_rects[idx] = rect
            self._draw_card(rect, idx, preview)

    def _draw_card(self, rect: pygame.Rect, idx: int, preview: dict):
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        border_color = self.CARD_BORDER
        locked_players = [i for i, choice in enumerate(self.selection) if choice == idx and self.locked_in[i]]
        pending = (
            not self.done
            and self.current_player < self.num_players
            and self.selection[self.current_player] == idx
            and not self.locked_in[self.current_player]
        )
        if locked_players:
            player_index = locked_players[-1]
            border_color = self.PLAYER_COLORS[player_index % len(self.PLAYER_COLORS)]
        elif idx == self.active_card_idx or pending:
            border_color = self.CARD_ACTIVE_BORDER
        elif hovered:
            border_color = tuple(min(255, c + 30) for c in self.CARD_BORDER)

        pygame.draw.rect(self.screen, self.CARD_BG, rect, border_radius=18)
        pygame.draw.rect(self.screen, border_color, rect, 3, border_radius=18)

        anim_state = "run" if (idx == self.active_card_idx or pending) else "idle"
        animation = preview["animations"].get(anim_state) or preview["animations"].get("idle")
        if animation:
            frame = animation.image
            frame_rect = frame.get_rect(center=(rect.centerx, rect.top + rect.height // 2))
            self.screen.blit(frame, frame_rect)

        name_surf = self.font_body.render(preview["name"], True, (240, 240, 245))
        self.screen.blit(name_surf, name_surf.get_rect(center=(rect.centerx, rect.bottom - 28)))

        label_y = rect.top + 12
        for player_index in locked_players:
            label = f"P{player_index + 1} READY"
            color = self.PLAYER_COLORS[player_index % len(self.PLAYER_COLORS)]
            label_surf = self.font_small.render(label, True, color)
            self.screen.blit(label_surf, label_surf.get_rect(center=(rect.centerx, label_y)))
            label_y += label_surf.get_height() + 4

    def _draw_button(self):
        enabled = self._can_lock_current_player()
        color = self.BUTTON_IDLE if enabled else self.BUTTON_DISABLED
        pygame.draw.rect(self.screen, color, self.button_rect, border_radius=18)
        pygame.draw.rect(self.screen, (20, 20, 30), self.button_rect, 2, border_radius=18)

        if not self.done:
            label = f"Select Player {self.current_player + 1}"
        else:
            label = "Continue"
        text_color = (0, 0, 0) if enabled else (200, 200, 210)
        label_surf = self.font_body.render(label, True, text_color)
        self.screen.blit(label_surf, label_surf.get_rect(center=self.button_rect.center))

    def _draw_tips(self):
        tips = ["Click a card to preview the run animation", "Press Enter or the button to lock in"]
        if self.num_players > 1:
            tips.append("Each player locks in separately")
        for idx, text in enumerate(tips):
            surf = self.font_small.render(text, True, (170, 170, 185))
            self.screen.blit(surf, (32, self.height - 110 + idx * 24))

    # ── animation/update helpers ───────────────────────────────────────────

    def _update_animations(self, dt: float):
        for preview in self.previews:
            for animation in preview["animations"].values():
                if animation:
                    animation.update(dt)

    def _build_result(self) -> list[str]:
        if not self.selection:
            return [DEFAULT_CHARACTER_NAME]
        resolved = []
        for idx in self.selection:
            if idx is None or not (0 <= idx < len(self.characters)):
                resolved.append(DEFAULT_CHARACTER_NAME)
            else:
                resolved.append(self.characters[idx])
        return resolved
