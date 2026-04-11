from __future__ import annotations

import math
import random

import pygame

from audio import get_audio
from settings import (
    MUSIC_PATH,
    TUTORIAL_VIDEO_PATH,
    WINDOW_SIZE,
    TARGET_FPS,
    SCENE_FADE_SPEED,
    SCENE_OVERLAY_COLOR,
    TITLE_TEXT,
    TITLE_BG_COLOR,
    TITLE_BG_IMAGE_PATH,
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
from .common import SceneAudioOverlay, _draw_rounded_rect, _load_font


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
        self._quit_requested = False
        self._audio_overlay = SceneAudioOverlay()

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
        self._tutorial_button_rect = pygame.Rect(24, self.height - 124, 190, 46)
        self._back_button_rect = pygame.Rect(24, self.height - 68, 150, 46)

        # First time playing prompt
        self._show_tutorial_prompt = True
        # Adjust tutorial prompt box dimensions
        self._prompt_yes_rect = pygame.Rect(0, 0, 100, 40)  # Smaller width and height
        self._prompt_no_rect = pygame.Rect(0, 0, 100, 40)  # Smaller width and height
        self._tutorial_pages = [
            "Welcome to Grid Survival!\nObjective: Survive as the tiles collapse beneath you.",
            "Controls:\nPlayer 1: W/A/S/D to move, SPACE to jump, Q for powers.\nPlayer 2: Arrows to move, RIGHT SHIFT to jump, / for powers.",
            "Modes:\n- Solo vs AI: Practice against bots.\n- Local: Couch Co-op with a friend.\n- LAN: Play over the local network.\n- Campaign: Story mode coming soon.",
            "Power-ups (Orbs): Collect glowing orbs to unlock powers.\n- Void Walk: Cross missing tiles.\n- Shields: Block one hazard hit.",
            "Hazards & Enemies:\nWatch out for crumbling tiles, the deadly shoreline, and enemy attacks!",
            "Would you like to watch the gameplay video tutorial?"
        ]

        # Load background
        self._bg_image = None
        if TITLE_BG_IMAGE_PATH.exists():
            try:
                raw_bg = pygame.image.load(str(TITLE_BG_IMAGE_PATH)).convert()
                # Scale to fill (cover)
                img_w, img_h = raw_bg.get_size()
                scale_w = self.width / img_w
                scale_h = self.height / img_h
                scale = max(scale_w, scale_h)
                new_w, new_h = int(img_w * scale), int(img_h * scale)
                scaled_bg = pygame.transform.smoothscale(raw_bg, (new_w, new_h))
                # Center crop
                crop_x = (new_w - self.width) // 2
                crop_y = (new_h - self.height) // 2
                self._bg_image = scaled_bg.subsurface((crop_x, crop_y, self.width, self.height))
            except Exception as e:
                print(f"Failed to load title bg: {e}")

    # ── music ────────────────────────────────────────────────────────────

    def _start_music(self) -> None:
        self.audio.play_music(
            track=MUSIC_PATH,
            loop=True,
            fade_ms=1500,
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
        if self._bg_image:
            self.screen.blit(self._bg_image, (0, 0))
            # Overlay
            overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 115))  # rgba(0, 0, 0, 0.45) -> 255 * 0.45 = 114.75
            self.screen.blit(overlay, (0, 0))
        else:
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

        self._draw_controls_panel()
        self._draw_tutorial_button()
        self._draw_back_button()
        self._audio_overlay.draw(self.screen)

    def _draw_controls_panel(self) -> None:
        panel_w = 420
        panel_h = 156
        panel_rect = pygame.Rect(self.width - panel_w - 24, self.height - panel_h - 44, panel_w, panel_h)
        bg_color = (16, 20, 34, 232)
        border_color = (120, 150, 200)
        _draw_rounded_rect(self.screen, panel_rect, bg_color, border_color, 2, 16)

        title_surf = self._font_body.render("CONTROLS", True, (245, 245, 255))
        title_rect = title_surf.get_rect(centerx=panel_rect.centerx, top=panel_rect.top + 10)
        self.screen.blit(title_surf, title_rect)

        pygame.draw.line(
            self.screen,
            (90, 115, 160),
            (panel_rect.left + 14, title_rect.bottom + 8),
            (panel_rect.right - 14, title_rect.bottom + 8),
            1,
        )

        column_w = (panel_rect.width - 28) // 2
        left_x = panel_rect.left + 14
        right_x = left_x + column_w
        rows_y = title_rect.bottom + 18

        self._draw_control_column(
            left_x,
            rows_y,
            "PLAYER 1",
            (255, 200, 0),
            [
                ("MOVE", "WASD"),
                ("JUMP", "SPACE"),
                ("POWER", "Q"),
            ],
        )
        self._draw_control_column(
            right_x,
            rows_y,
            "PLAYER 2",
            (100, 220, 255),
            [
                ("MOVE", "ARROWS"),
                ("JUMP", "RSHIFT"),
                ("POWER", "SLASH"),
            ],
        )

    def _draw_control_column(self, x: int, y: int, heading: str, heading_color: tuple, rows: list[tuple[str, str]]) -> None:
        heading_surf = self._font_small.render(heading, True, heading_color)
        self.screen.blit(heading_surf, (x, y))

        cursor_y = y + heading_surf.get_height() + 8
        for label, value in rows:
            label_surf = self._font_small.render(f"{label}:", True, INPUT_LABEL_COLOR)
            value_surf = self._font_small.render(value, True, INPUT_TEXT_COLOR)
            self.screen.blit(label_surf, (x, cursor_y))
            self.screen.blit(value_surf, (x + 76, cursor_y))
            cursor_y += max(label_surf.get_height(), value_surf.get_height()) + 6

    def _draw_tutorial_prompt(self) -> None:
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))

        panel_w, panel_h = 800, 300
        panel_rect = pygame.Rect((self.width - panel_w) // 2, (self.height - panel_h) // 2, panel_w, panel_h)
        _draw_rounded_rect(self.screen, panel_rect, (25, 30, 45), (100, 150, 255), 3, 16)

        question_surf = self._font_heading.render("Is this your first time playing?", True, (255, 255, 255))
        self.screen.blit(question_surf, question_surf.get_rect(center=(self.width // 2, panel_rect.top + 80)))

        self._prompt_yes_rect.center = (self.width // 2 - 120, panel_rect.bottom - 80)
        self._prompt_no_rect.center = (self.width // 2 + 120, panel_rect.bottom - 80)

        mouse_pos = pygame.mouse.get_pos()
        
        yes_hover = self._prompt_yes_rect.collidepoint(mouse_pos)
        yes_bg = (50, 120, 60) if yes_hover else (30, 80, 40)
        _draw_rounded_rect(self.screen, self._prompt_yes_rect, yes_bg, (100, 255, 100), 2, 8)
        yes_surf = self._font_body.render("YES", True, (255, 255, 255))
        self.screen.blit(yes_surf, yes_surf.get_rect(center=self._prompt_yes_rect.center))

        no_hover = self._prompt_no_rect.collidepoint(mouse_pos)
        no_bg = (150, 50, 50) if no_hover else (100, 30, 30)
        _draw_rounded_rect(self.screen, self._prompt_no_rect, no_bg, (255, 100, 100), 2, 8)
        no_surf = self._font_body.render("NO", True, (255, 255, 255))
        self.screen.blit(no_surf, no_surf.get_rect(center=self._prompt_no_rect.center))

    def _play_multipage_tutorial(self) -> None:
        import sys
        import math
        from pathlib import Path

        current_page = 0
        is_viewing = True

        # Helper to load images safely
        def safe_load(path_str, scale=1.0):
            p = Path(path_str)
            if p.exists():
                img = pygame.image.load(str(p)).convert_alpha()
                if scale != 1.0:
                    w, h = img.get_size()
                    img = pygame.transform.smoothscale(img, (int(w * scale), int(h * scale)))
                return img
            return None

        # Load tutorial assets inside the method so it doesn't slow down the main boot
        img_block = safe_load("Assets/Blocks/10.png", 0.6)
        img_caveman = safe_load("Assets/Characters/portait/Caveman.png", 0.6)
        img_ninja = safe_load("Assets/Characters/portait/Ninja.png", 0.6)
        img_goblin = safe_load("Assets/Characters/portait/Giant Goblin.png", 0.6)
        
        img_orbs = []
        # Adjusted orb scaling so they don't overshadow anything
        for orb_name in ["power.png", "phase.png", "shield.png"]:
            orb = safe_load(f"Assets/orbs/{orb_name}", 0.45) 
            if orb: img_orbs.append(orb)

        anim_timer = 0.0

        prompt_yes_rect = pygame.Rect(0, 0, 120, 50)
        prompt_no_rect = pygame.Rect(0, 0, 120, 50)

        while is_viewing:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            anim_timer += dt

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if current_page == 5:
                        if prompt_yes_rect.collidepoint(event.pos):
                            self._play_tutorial_video()
                            is_viewing = False
                            continue
                        elif prompt_no_rect.collidepoint(event.pos):
                            is_viewing = False
                            continue
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_RIGHT):
                        if current_page < 5:
                            current_page += 1
                        else:
                            # Default to yes on enter for last page
                            self._play_tutorial_video()
                            is_viewing = False
                        continue
                    elif event.key == pygame.K_ESCAPE:
                        is_viewing = False
                        continue

            if not is_viewing:
                break

            # Keep title animations alive behind the tutorial panel
            self._title_time += dt
            self._update_particles(dt)

            self.screen.fill((10, 15, 25))
            self._draw_background()
            self._draw_title()

            dimmer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            dimmer.fill((0, 0, 0, 180))  # Slightly darker overlay
            self.screen.blit(dimmer, (0, 0))

            panel_w, panel_h = 1000, 520
            panel_rect = pygame.Rect((self.width - panel_w) // 2, (self.height - panel_h) // 2, panel_w, panel_h)
            _draw_rounded_rect(self.screen, panel_rect, (20, 25, 35, 240), (150, 200, 255), 3, 15)
            
            # Draw specific visual animations per tutorial page
            visual_y = panel_rect.top + 100
            text_y_start = visual_y + 120

            if current_page == 0 and img_block:
                # Bouncing tile
                bounce = math.sin(anim_timer * 4) * 15
                self.screen.blit(img_block, img_block.get_rect(center=(self.width // 2, visual_y + bounce)))
            elif current_page == 1 and img_caveman:
                # Bouncing character portraits for Player 1 / Player 2
                bounce_1 = math.sin(anim_timer * 5) * 10
                bounce_2 = math.cos(anim_timer * 5) * 10
                self.screen.blit(img_caveman, img_caveman.get_rect(center=(self.width // 2 - 120, visual_y + bounce_1)))
                if img_ninja:
                    self.screen.blit(img_ninja, img_ninja.get_rect(center=(self.width // 2 + 120, visual_y + bounce_2)))
            elif current_page == 2:
                # Bouncing stylized Mode "Cards"
                modes = [("SOLO", (80, 160, 255)), ("CO-OP", (255, 140, 80)), ("LAN", (100, 255, 140))]
                for i, (text, color) in enumerate(modes):
                    px = self.width // 2 - 180 + i * 180
                    py = visual_y - 20 + math.sin(anim_timer * 3 + i) * 10
                    rect = pygame.Rect(0, 0, 140, 80)
                    rect.center = (px, py)
                    _draw_rounded_rect(self.screen, rect, (30, 40, 60), color, 2, 10)
                    
                    # Draw Icons
                    cx, cy = px, py - 12
                    if text == "SOLO":
                        pygame.draw.circle(self.screen, color, (cx, cy - 6), 8)
                        pygame.draw.rect(self.screen, color, (cx - 10, cy + 4, 20, 12), border_radius=4)
                    elif text == "CO-OP":
                        pygame.draw.circle(self.screen, color, (cx - 12, cy - 6), 8)
                        pygame.draw.rect(self.screen, color, (cx - 22, cy + 4, 20, 12), border_radius=4)
                        pygame.draw.circle(self.screen, color, (cx + 12, cy - 6), 8)
                        pygame.draw.rect(self.screen, color, (cx + 2, cy + 4, 20, 12), border_radius=4)
                    elif text == "LAN":
                        # Draw connected nodes/screens
                        pygame.draw.rect(self.screen, color, (cx - 8, cy - 12, 16, 12), border_radius=2)
                        pygame.draw.rect(self.screen, color, (cx - 20, cy + 4, 16, 12), border_radius=2)
                        pygame.draw.rect(self.screen, color, (cx + 4, cy + 4, 16, 12), border_radius=2)
                        pygame.draw.line(self.screen, color, (cx, cy), (cx, cy + 4), 2)
                        pygame.draw.line(self.screen, color, (cx - 12, cy + 4), (cx + 12, cy + 4), 2)
                    
                    label_surf = self._font_small.render(text, True, (240, 240, 255))
                    self.screen.blit(label_surf, label_surf.get_rect(center=(px, py + 24)))
                text_y_start -= 40
            elif current_page == 3 and img_orbs:
                # Row of hovering Orbs (instead of circling)
                for i, img in enumerate(img_orbs):
                    px = self.width // 2 - 120 + i * 120
                    py = visual_y - 40 + math.sin(anim_timer * 4 + i) * 8
                    self.screen.blit(img, img.get_rect(center=(px, py)))
            elif current_page == 4:
                # Render hazards and enemy representations
                bounce_1 = math.sin(anim_timer * 4) * 10
                bounce_2 = math.cos(anim_timer * 4) * 10
                
                if img_goblin:
                    self.screen.blit(img_goblin, img_goblin.get_rect(center=(self.width // 2 - 100, visual_y + bounce_1)))
                if img_block:
                    # Tint the block red to represent a crumbling/hazard block
                    hazard_block = img_block.copy()
                    hazard_block.fill((200, 50, 50), special_flags=pygame.BLEND_MULT)
                    self.screen.blit(hazard_block, hazard_block.get_rect(center=(self.width // 2 + 100, visual_y + bounce_2)))
                    
                pulse = 155 + int(100 * math.sin(anim_timer * 6))
                warning_surf = self._font_display.render("!", True, (pulse, 50, 50))
                self.screen.blit(warning_surf, warning_surf.get_rect(center=(self.width // 2, visual_y - 50)))
            elif current_page == 5:
                # Video prompt styling
                prompt_yes_rect.center = (self.width // 2 - 90, panel_rect.bottom - 90)
                prompt_no_rect.center = (self.width // 2 + 90, panel_rect.bottom - 90)

                mouse_pos = pygame.mouse.get_pos()
                
                yes_hover = prompt_yes_rect.collidepoint(mouse_pos)
                yes_bg = (50, 120, 60) if yes_hover else (30, 80, 40)
                _draw_rounded_rect(self.screen, prompt_yes_rect, yes_bg, (100, 255, 100), 2, 8)
                yes_surf = self._font_body.render("YES", True, (255, 255, 255))
                self.screen.blit(yes_surf, yes_surf.get_rect(center=prompt_yes_rect.center))

                no_hover = prompt_no_rect.collidepoint(mouse_pos)
                no_bg = (150, 50, 50) if no_hover else (100, 30, 30)
                _draw_rounded_rect(self.screen, prompt_no_rect, no_bg, (255, 100, 100), 2, 8)
                no_surf = self._font_body.render("NO", True, (255, 255, 255))
                self.screen.blit(no_surf, no_surf.get_rect(center=prompt_no_rect.center))
                
                # Draw video icon
                icon_y = visual_y + math.sin(anim_timer * 3) * 5
                pygame.draw.rect(self.screen, (220, 50, 50), (self.width // 2 - 30, icon_y - 20, 60, 40), border_radius=6)
                pygame.draw.polygon(self.screen, (255, 255, 255), [(self.width // 2 - 5, icon_y - 10), (self.width // 2 - 5, icon_y + 10), (self.width // 2 + 10, icon_y)])
                text_y_start -= 20

            # Render tutorial text dynamically under animations
            lines = self._tutorial_pages[current_page].split('\n')
            for line in lines:
                text_surf = self._font_body.render(line, True, (230, 240, 255))
                self.screen.blit(text_surf, text_surf.get_rect(center=(self.width // 2, text_y_start)))
                text_y_start += 45
            
            # Progress instruction
            if current_page < 5:
                sub_surf = self._font_small.render(f"Page {current_page + 1} of {len(self._tutorial_pages)-1} - Press ENTER to continue", True, (150, 180, 210))
                self.screen.blit(sub_surf, sub_surf.get_rect(center=(self.width // 2, panel_rect.bottom - 40)))

            self._audio_overlay.draw(self.screen)
            pygame.display.flip()

    def _draw_back_button(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        hovered = self._back_button_rect.collidepoint(mouse_pos)
        base_color = (30, 35, 55, 210)
        hover_color = (60, 70, 100, 230)
        bg_color = hover_color if hovered else base_color
        border_color = (140, 150, 190)
        _draw_rounded_rect(self.screen, self._back_button_rect, bg_color, border_color, 2, 14)
        label = self._font_small.render("EXIT", True, (235, 235, 245))
        self.screen.blit(label, label.get_rect(center=self._back_button_rect.center))

    def _draw_tutorial_button(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        hovered = self._tutorial_button_rect.collidepoint(mouse_pos)
        base_color = (30, 45, 70, 210)
        hover_color = (60, 90, 130, 230)
        bg_color = hover_color if hovered else base_color
        border_color = (120, 170, 220)
        _draw_rounded_rect(self.screen, self._tutorial_button_rect, bg_color, border_color, 2, 14)
        label = self._font_small.render("TUTORIAL", True, (235, 240, 250))
        self.screen.blit(label, label.get_rect(center=self._tutorial_button_rect.center))

    def _play_tutorial_video(self) -> None:
        if not TUTORIAL_VIDEO_PATH.exists():
            self.warning_text = "TUTORIAL VIDEO NOT FOUND"
            self.warning_timer = WARNING_DISPLAY_DURATION
            return

        try:
            import importlib

            cv2 = importlib.import_module("cv2")
        except Exception:
            self.warning_text = "INSTALL OPENCV: pip install opencv-python"
            self.warning_timer = WARNING_DISPLAY_DURATION
            return

        capture = cv2.VideoCapture(str(TUTORIAL_VIDEO_PATH))
        if not capture.isOpened():
            self.warning_text = "FAILED TO OPEN TUTORIAL VIDEO"
            self.warning_timer = WARNING_DISPLAY_DURATION
            return

        fps = capture.get(cv2.CAP_PROP_FPS)
        if fps <= 1 or fps > 120:
            fps = 30.0
        target_fps = max(15, min(60, int(round(fps))))
        frame_clock = pygame.time.Clock()

        panel_w = int(self.width * 0.72)
        panel_h = int(self.height * 0.72)
        panel_rect = pygame.Rect((self.width - panel_w) // 2, (self.height - panel_h) // 2, panel_w, panel_h)
        header_h = 48
        padding = 16
        content_rect = pygame.Rect(
            panel_rect.left + padding,
            panel_rect.top + header_h + 8,
            panel_rect.width - padding * 2,
            panel_rect.height - header_h - padding - 8,
        )
        is_running = True

        while is_running:
            dt = frame_clock.tick(target_fps) / 1000.0
            close_rect = pygame.Rect(panel_rect.right - 104, panel_rect.top + 10, 88, 30)
            for event in pygame.event.get():
                if self._audio_overlay.handle_event(event):
                    continue
                if event.type == pygame.QUIT:
                    self._quit_requested = True
                    is_running = False
                    break
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                    is_running = False
                    break
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if close_rect.collidepoint(event.pos):
                        is_running = False
                        break

            if not is_running:
                break

            ok, frame = capture.read()
            if not ok:
                break

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_h, frame_w = frame_rgb.shape[:2]
            frame_surface = pygame.image.frombuffer(frame_rgb.tobytes(), (frame_w, frame_h), "RGB")

            scale = min(content_rect.width / frame_w, content_rect.height / frame_h)
            draw_w = max(1, int(frame_w * scale))
            draw_h = max(1, int(frame_h * scale))
            if draw_w != frame_w or draw_h != frame_h:
                frame_surface = pygame.transform.smoothscale(frame_surface, (draw_w, draw_h))

            draw_x = content_rect.left + (content_rect.width - draw_w) // 2
            draw_y = content_rect.top + (content_rect.height - draw_h) // 2

            # Keep title animations alive behind the tutorial panel.
            self._title_time += dt
            self.warning_timer = max(0.0, self.warning_timer - dt)
            self._cursor_timer += dt
            if self._cursor_timer >= 1.0 / CURSOR_BLINK_SPEED:
                self._cursor_timer = 0.0
                self._cursor_visible = not self._cursor_visible
            self._update_shake(dt)
            self._update_particles(dt)

            self._draw_background()
            self._draw_title()
            self._draw_input()

            dimmer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            dimmer.fill((0, 0, 0, 140))
            self.screen.blit(dimmer, (0, 0))

            _draw_rounded_rect(self.screen, panel_rect, (14, 20, 34, 240), (125, 165, 220), 2, 14)
            pygame.draw.rect(self.screen, (5, 8, 14), content_rect, border_radius=8)
            self.screen.blit(frame_surface, (draw_x, draw_y))

            heading = self._font_small.render("TUTORIAL", True, (235, 240, 250))
            self.screen.blit(heading, (panel_rect.left + 16, panel_rect.top + 14))

            hovered_close = close_rect.collidepoint(pygame.mouse.get_pos())
            close_bg = (180, 70, 70, 235) if hovered_close else (130, 56, 56, 220)
            close_border = (245, 170, 170)
            _draw_rounded_rect(self.screen, close_rect, close_bg, close_border, 2, 10)
            close_text = self._font_small.render("CLOSE", True, (245, 245, 245))
            self.screen.blit(close_text, close_text.get_rect(center=close_rect.center))

            self._audio_overlay.draw(self.screen)

            pygame.display.flip()

        capture.release()

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
                if self._audio_overlay.handle_event(event):
                    continue
                if event.type == pygame.QUIT:
                    return None
                
                # Check tutorial prompt intercept first
                if self._show_tutorial_prompt:
                    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        if self._prompt_yes_rect.collidepoint(event.pos):
                            self._show_tutorial_prompt = False
                            self._play_multipage_tutorial()
                        elif self._prompt_no_rect.collidepoint(event.pos):
                            self._show_tutorial_prompt = False
                    continue

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._tutorial_button_rect.collidepoint(event.pos):
                        self._play_multipage_tutorial()
                        continue
                    if self._back_button_rect.collidepoint(event.pos):
                        self._fade("out")
                        return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._fade("out")
                        return None
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
            
            if self._show_tutorial_prompt:
                self._draw_tutorial_prompt()

            pygame.display.flip()


__all__ = ["TitleScreen"]
