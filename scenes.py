import math
import random

import pygame

from settings import (
    INPUT_BOX_BG_COLOR,
    INPUT_BOX_BORDER_COLOR,
    INPUT_BOX_HEIGHT,
    INPUT_BOX_WIDTH,
    INPUT_LABEL_COLOR,
    INPUT_TEXT_COLOR,
    INPUT_FONT_SIZE,
    MODE_BG_COLOR,
    MODE_CARD_BASE_COLOR,
    MODE_CARD_BORDER_COLOR,
    MODE_CARD_CLICK_BASE,
    MODE_CARD_DESC_COLOR,
    MODE_CARD_HEIGHT,
    MODE_CARD_HOVER_COLOR,
    MODE_CARD_SPACING,
    MODE_CARD_TITLE_COLOR,
    MODE_CARD_WIDTH,
    MODE_CARD_DESC_SIZE,
    MODE_CARD_TITLE_SIZE,
    MODE_HEADER_FONT_SIZE,
    MODE_HEADER_COLOR,
    MODE_LOCAL_MULTIPLAYER,
    MODE_ONLINE_MULTIPLAYER,
    MODE_SUBTITLE_FONT_SIZE,
    MODE_SUBTITLE_COLOR,
    MODE_VS_COMPUTER,
    MUSIC_PATH,
    MUSIC_VOLUME,
    SCENE_OVERLAY_COLOR,
    MODE_CLICK_FLASH_TIME,
    NAME_MAX_LENGTH,
    PROMPT_BLINK_SPEED,
    PROMPT_TEXT_COLOR,
    SCENE_FADE_SPEED,
    TARGET_FPS,
    TITLE_BG_COLOR,
    TITLE_COLORS,
    TITLE_DROP_DURATION,
    TITLE_FONT_SIZE,
    TITLE_PARTICLE_COUNT,
    TITLE_PARTICLE_MAX_SIZE,
    TITLE_PARTICLE_MAX_SPEED,
    TITLE_PARTICLE_MIN_SIZE,
    TITLE_PARTICLE_MIN_SPEED,
    TITLE_PULSE_SPEED,
    TITLE_PARTICLE_COLOR_BASE,
    TITLE_SUBTITLE_COLOR,
    TITLE_SUB_FONT_SIZE,
    TITLE_TEXT,
    WARNING_TEXT_COLOR,
    WARNING_FONT_SIZE,
    WINDOW_SIZE,
)


class TitleScreen:
    """Opening title screen with animated logo, particles, and name entry."""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock):
        self.screen = screen
        self.clock = clock
        self.width, self.height = WINDOW_SIZE

        self.title_font = pygame.font.SysFont("impact", TITLE_FONT_SIZE, bold=True)
        self.sub_font = pygame.font.SysFont("consolas", TITLE_SUB_FONT_SIZE, bold=True)
        self.input_font = pygame.font.SysFont("consolas", INPUT_FONT_SIZE, bold=True)
        self.warning_font = pygame.font.SysFont("consolas", WARNING_FONT_SIZE, bold=True)

        self.player_name = ""
        self.warning_text = ""
        self.warning_timer = 0.0
        self._title_time = 0.0

        self._letters = []
        self._build_title_letters()

        self._particles = []
        self._spawn_particles(TITLE_PARTICLE_COUNT)

        self._start_music()

    def _start_music(self) -> None:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            if MUSIC_PATH.exists():
                pygame.mixer.music.load(str(MUSIC_PATH))
                pygame.mixer.music.set_volume(MUSIC_VOLUME)
                pygame.mixer.music.play(-1)
            else:
                print(f"Music file not found: {MUSIC_PATH}")
        except pygame.error as err:
            print(f"Music init/load failed: {err}")

    def _build_title_letters(self) -> None:
        letter_spacing = 52
        start_x = self.width // 2 - ((len(TITLE_TEXT) - 1) * letter_spacing) // 2
        base_y = 130

        for idx, ch in enumerate(TITLE_TEXT):
            if ch == " ":
                continue
            x = start_x + idx * letter_spacing
            self._letters.append(
                {
                    "char": ch,
                    "x": x,
                    "base_y": base_y,
                    "start_delay": idx * 0.05,
                }
            )

    def _spawn_particles(self, count: int) -> None:
        for _ in range(count):
            self._particles.append(
                {
                    "x": random.uniform(80, self.width - 80),
                    "y": random.uniform(180, self.height - 120),
                    "size": random.randint(TITLE_PARTICLE_MIN_SIZE, TITLE_PARTICLE_MAX_SIZE),
                    "speed": random.uniform(TITLE_PARTICLE_MIN_SPEED, TITLE_PARTICLE_MAX_SPEED),
                    "phase": random.uniform(0, math.pi * 2),
                }
            )

    def _update_particles(self, dt: float) -> None:
        for p in self._particles:
            p["y"] -= p["speed"] * dt
            p["x"] += math.sin(self._title_time * 2.0 + p["phase"]) * 18 * dt
            if p["y"] < 120:
                p["y"] = self.height - 80
                p["x"] = random.uniform(80, self.width - 80)

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
        pulse = 1.0 + 0.08 * math.sin(self._title_time * TITLE_PULSE_SPEED)
        color_index = int(self._title_time * 3.0) % len(TITLE_COLORS)
        base_color = TITLE_COLORS[color_index]

        for idx, info in enumerate(self._letters):
            t = max(0.0, self._title_time - info["start_delay"])
            drop_progress = min(1.0, t / TITLE_DROP_DURATION)
            ease = 1 - (1 - drop_progress) ** 3
            y = -80 + (info["base_y"] + 80) * ease
            bounce = 7 * math.sin(self._title_time * 9 + idx) * (1.0 - drop_progress)

            letter = info["char"]
            color = (
                min(255, base_color[0] + idx * 2),
                max(0, base_color[1] - idx),
                base_color[2],
            )
            surf = self.title_font.render(letter, True, color)
            w, h = surf.get_size()
            surf = pygame.transform.smoothscale(
                surf,
                (max(1, int(w * pulse)), max(1, int(h * pulse))),
            )
            rect = surf.get_rect(center=(info["x"], y + bounce))
            self.screen.blit(surf, rect)

        subtitle = self.sub_font.render("Survive the collapsing platform", True, TITLE_SUBTITLE_COLOR)
        self.screen.blit(subtitle, subtitle.get_rect(center=(self.width // 2, 220)))

    def _draw_input(self) -> None:
        label = self.input_font.render("Enter Your Name:", True, INPUT_LABEL_COLOR)
        self.screen.blit(label, label.get_rect(center=(self.width // 2, 320)))

        box_rect = pygame.Rect(0, 0, INPUT_BOX_WIDTH, INPUT_BOX_HEIGHT)
        box_rect.center = (self.width // 2, 385)
        pygame.draw.rect(self.screen, INPUT_BOX_BG_COLOR, box_rect, border_radius=10)
        pygame.draw.rect(self.screen, INPUT_BOX_BORDER_COLOR, box_rect, 3, border_radius=10)

        typed = self.player_name if self.player_name else "_"
        name_text = self.input_font.render(typed, True, INPUT_TEXT_COLOR)
        self.screen.blit(name_text, name_text.get_rect(midleft=(box_rect.left + 14, box_rect.centery)))

        prompt_alpha = 130 + int(125 * abs(math.sin(self._title_time * PROMPT_BLINK_SPEED)))
        prompt_surface = self.sub_font.render("PRESS ENTER TO CONTINUE", True, PROMPT_TEXT_COLOR)
        prompt_surface.set_alpha(prompt_alpha)
        self.screen.blit(prompt_surface, prompt_surface.get_rect(center=(self.width // 2, 465)))

        if self.warning_text and self.warning_timer > 0:
            warn = self.warning_font.render(self.warning_text, True, WARNING_TEXT_COLOR)
            self.screen.blit(warn, warn.get_rect(center=(self.width // 2, 515)))

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

    def run(self):
        self._fade("in")

        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._title_time += dt
            self.warning_timer = max(0.0, self.warning_timer - dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        if self.player_name.strip():
                            self._fade("out")
                            return self.player_name.strip()
                        self.warning_text = "Please enter your name to continue"
                        self.warning_timer = 1.8
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


class ModeSelectionScreen:
    """Mode select screen shown after successful name entry."""

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock, player_name: str):
        self.screen = screen
        self.clock = clock
        self.player_name = player_name
        self.width, self.height = WINDOW_SIZE

        self.header_font = pygame.font.SysFont("impact", MODE_HEADER_FONT_SIZE, bold=True)
        self.sub_font = pygame.font.SysFont("consolas", MODE_SUBTITLE_FONT_SIZE, bold=True)
        self.card_title_font = pygame.font.SysFont("consolas", MODE_CARD_TITLE_SIZE, bold=True)
        self.card_desc_font = pygame.font.SysFont("consolas", MODE_CARD_DESC_SIZE)

        card_w = MODE_CARD_WIDTH
        card_h = MODE_CARD_HEIGHT
        center_x = self.width // 2 - card_w // 2
        start_y = 240
        spacing = MODE_CARD_SPACING

        self.cards = [
            {
                "mode": MODE_VS_COMPUTER,
                "title": "[1] VS COMPUTER",
                "desc": "Face an AI-controlled opponent.",
                "rect": pygame.Rect(center_x, start_y + spacing * 0, card_w, card_h),
            },
            {
                "mode": MODE_LOCAL_MULTIPLAYER,
                "title": "[2] LOCAL MULTIPLAYER",
                "desc": "Play with another player on this keyboard.",
                "rect": pygame.Rect(center_x, start_y + spacing * 1, card_w, card_h),
            },
            {
                "mode": MODE_ONLINE_MULTIPLAYER,
                "title": "[3] ONLINE MULTIPLAYER",
                "desc": "Play with another player over LAN/Internet.",
                "rect": pygame.Rect(center_x, start_y + spacing * 2, card_w, card_h),
            },
        ]

        self._fade_alpha = 255
        self._clicked_mode = None
        self._flash_timer = 0.0

    def _draw(self) -> None:
        self.screen.fill(MODE_BG_COLOR)

        header = self.header_font.render(f"Welcome, {self.player_name}!", True, MODE_HEADER_COLOR)
        self.screen.blit(header, header.get_rect(center=(self.width // 2, 95)))

        subtitle = self.sub_font.render("Choose Your Game Mode:", True, MODE_SUBTITLE_COLOR)
        self.screen.blit(subtitle, subtitle.get_rect(center=(self.width // 2, 150)))

        mouse_pos = pygame.mouse.get_pos()
        for card in self.cards:
            rect = card["rect"]
            hovered = rect.collidepoint(mouse_pos)
            selected = self._clicked_mode == card["mode"]

            base = MODE_CARD_BASE_COLOR
            if hovered:
                base = MODE_CARD_HOVER_COLOR
            if selected:
                pulse = 0.5 + 0.5 * math.sin(self._flash_timer * 20)
                base = (
                    int(MODE_CARD_CLICK_BASE[0] + 80 * pulse),
                    int(MODE_CARD_CLICK_BASE[1] + 80 * pulse),
                    int(MODE_CARD_CLICK_BASE[2] + 40 * pulse),
                )

            pygame.draw.rect(self.screen, base, rect, border_radius=12)
            pygame.draw.rect(self.screen, MODE_CARD_BORDER_COLOR, rect, 2, border_radius=12)

            title = self.card_title_font.render(card["title"], True, MODE_CARD_TITLE_COLOR)
            desc = self.card_desc_font.render(card["desc"], True, MODE_CARD_DESC_COLOR)
            self.screen.blit(title, title.get_rect(midleft=(rect.left + 18, rect.top + 38)))
            self.screen.blit(desc, desc.get_rect(midleft=(rect.left + 18, rect.top + 78)))

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

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_1:
                        self._clicked_mode = MODE_VS_COMPUTER
                    elif event.key == pygame.K_2:
                        self._clicked_mode = MODE_LOCAL_MULTIPLAYER
                    elif event.key == pygame.K_3:
                        self._clicked_mode = MODE_ONLINE_MULTIPLAYER
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for card in self.cards:
                        if card["rect"].collidepoint(event.pos):
                            self._clicked_mode = card["mode"]
                            break

            self._draw()
            pygame.display.flip()

            if self._clicked_mode is not None:
                # brief click flash
                flash_elapsed = 0.0
                while flash_elapsed < MODE_CLICK_FLASH_TIME:
                    fdt = self.clock.tick(TARGET_FPS) / 1000.0
                    flash_elapsed += fdt
                    self._flash_timer += fdt
                    self._draw()
                    pygame.display.flip()

                self._fade(False)
                return self._clicked_mode
