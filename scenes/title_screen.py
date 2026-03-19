from __future__ import annotations

import math
import random

import pygame

from audio import get_audio
from settings import (
    MUSIC_PATH,
    MUSIC_VOLUME,
    WINDOW_SIZE,
    TARGET_FPS,
    SCENE_FADE_SPEED,
    SCENE_OVERLAY_COLOR,
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
    NAME_MAX_LENGTH,
    INPUT_BOX_WIDTH,
    INPUT_BOX_HEIGHT,
    INPUT_BOX_BG_COLOR,
    INPUT_BOX_BORDER_COLOR,
    INPUT_LABEL_COLOR,
    INPUT_TEXT_COLOR,
    PROMPT_TEXT_COLOR,
    PROMPT_BLINK_SPEED,
    WARNING_TEXT_COLOR,
    WARNING_DISPLAY_DURATION,
    CURSOR_BLINK_SPEED,
    FONT_PATH_DISPLAY,
    FONT_PATH_HEADING,
    FONT_PATH_BODY,
    FONT_PATH_SMALL,
    FONT_SIZE_DISPLAY,
    FONT_SIZE_HEADING,
    FONT_SIZE_BODY,
    FONT_SIZE_SMALL,
)
from .common import _draw_rounded_rect, _load_font


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

    # ── music ────────────────────────────────────────────────────────────

    def _start_music(self) -> None:
        self.audio.play_music(
            track=MUSIC_PATH,
            loop=True,
            fade_ms=1500,
            volume=MUSIC_VOLUME,
        )

    # ── title letter setup ───────────────────────────────────────────────

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

    # ── particles ────────────────────────────────────────────────────────

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

    # ── drawing ──────────────────────────────────────────────────────────

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

    # ── shake update ─────────────────────────────────────────────────────

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

    # ── fade ─────────────────────────────────────────────────────────────

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

    # ── main loop ────────────────────────────────────────────────────────

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


__all__ = ["TitleScreen"]
