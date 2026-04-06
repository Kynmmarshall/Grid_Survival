from __future__ import annotations

import math
import random
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
    MODE_SURVIVAL,
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
CARD_HEIGHT = 370  # Taller for description
CARD_RADIUS = 24
CARD_GUTTER = 40
MAX_COLUMNS = 4
SUMMARY_PANEL_HEIGHT = 140

PREVIEW_SCALE = 0.45  # Larger sprites
PREVIEW_FRAME_DURATION = 1 / 18
PREVIEW_OFFSET_Y = -40  # Move sprite up
PLACEHOLDER_SIZE = (128, 128)

BUTTON_WIDTH = 240
BUTTON_HEIGHT = 60
BUTTON_RADIUS = 18
BUTTON_BG = (34, 52, 86)
BUTTON_BG_HOVER = (58, 84, 132)
BUTTON_BG_DISABLED = (20, 30, 48)
BUTTON_TEXT = (255, 255, 255)
BUTTON_TEXT_DISABLED = (140, 150, 180)

CHARACTER_METADATA = {
    "Caveman": {
        "color": (255, 160, 60),
        "ability": "Basic Smash",
        "icon": "🔨",
        "desc": "Destroys nearby warning tiles\nShockwave repels enemies",
    },
    "Giant Goblin": {
        "color": (140, 230, 80),
        "ability": "Toxic Gas", 
        "icon": "☠️",
        "desc": "Leaves a trail of poison\nImmune to hazard damage",
    },
    "Ninja": {
        "color": (100, 220, 255),
        "ability": "Shadow Dash",
        "icon": "⚡",
        "desc": "Blink forward instantly\nBrief invulnerability",
    },
    "Viking Leader": {
        "color": (255, 80, 80),
        "ability": "Battle Cry",
        "icon": "⚔️",
        "desc": "Stuns nearby enemies\nBoosts movement speed",
    }
}

MODE_HEADERS = {
    MODE_SURVIVAL: ("SURVIVAL MODE", ""),
    MODE_LOCAL_MULTIPLAYER: ("LOCAL MULTIPLAYER", ""),
    MODE_ONLINE_MULTIPLAYER: ("PLAY OVER LAN", ""),
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
        self.back_requested = False
        self.quit_requested = False

        self.mode_title, self.mode_hint = MODE_HEADERS.get(
            game_mode,
            MODE_HEADERS["default"],
        )

        # Force title for local multiplayer
        if self.game_mode == MODE_LOCAL_MULTIPLAYER:
            self.mode_title = "ASSEMBLE YOUR CREW"

        self.characters: List[str] = available_characters() or [DEFAULT_CHARACTER_NAME]
        self.cards: List[dict] = []
        self._build_cards()

        # Fonts
        self._font_heading = _load_font(FONT_PATH_HEADING, FONT_SIZE_HEADING + 12, bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, FONT_SIZE_BODY)
        self._font_small = _load_font(FONT_PATH_BODY, 18)

        # Background effects
        self.particles = []
        for _ in range(50):
            self.particles.append({
                "x": random.randint(0, self.width),
                "y": random.randint(0, self.height),
                "radius": random.randint(1, 3),
                "speed": random.uniform(0.2, 0.8),
                "alpha": random.randint(50, 150)
            })
        self._bg_gradient = self._create_gradient()

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
        self._closing = False

    # ── card + animation setup ──────────────────────────────────────────

    def _build_cards(self) -> None:
        if not self.characters:
            return
        cols = min(MAX_COLUMNS, max(1, len(self.characters)))
        rows = math.ceil(len(self.characters) / cols)
        grid_width = cols * CARD_WIDTH + (cols - 1) * CARD_GUTTER
        start_x = self.width // 2 - grid_width // 2
        start_y = 200  # Lowered to accommodate larger header

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

    def _create_gradient(self) -> pygame.Surface:
        gradient = pygame.Surface((1, self.height))
        # Rich dark gradient: dark navy/black to deep purple/blue
        color_top = (5, 8, 20)
        color_bottom = (25, 30, 60)

        for y in range(self.height):
            ratio = y / self.height
            r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
            g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
            b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
            gradient.set_at((0, y), (r, g, b))

        return pygame.transform.scale(gradient, (self.width, self.height))

    def _draw_background(self) -> None:
        if not hasattr(self, '_bg_gradient'):
            self._bg_gradient = self._create_gradient()
        self.screen.blit(self._bg_gradient, (0, 0))

        # Atmospheric glowing particles
        for p in self.particles:
            p["y"] -= p["speed"]
            p["x"] += math.sin(p["y"] * 0.02) * 0.3  # Slight drift
            
            # Wrap around
            if p["y"] < -10:
                p["y"] = self.height + 10
                p["x"] = random.randint(0, self.width)
            
            radius = p["radius"]
            # Draw soft glow
            surf = pygame.Surface((radius * 6, radius * 6), pygame.SRCALPHA)
            # Core
            pygame.draw.circle(surf, (180, 220, 255, p["alpha"]), (radius*3, radius*3), radius)
            # Outer glow
            pygame.draw.circle(surf, (100, 180, 255, p["alpha"] // 2), (radius*3, radius*3), radius * 2)
            
            self.screen.blit(surf, (p["x"] - radius*3, p["y"] - radius*3), special_flags=pygame.BLEND_ADD)

    def _draw_header(self) -> None:
        # Main Title with Glow
        title_surf = self._font_heading.render(self.mode_title, True, HEADER_COLOR)
        title_rect = title_surf.get_rect(center=(self.width // 2, 70))

        # Glow effect
        glow_surf = self._font_heading.render(self.mode_title, True, (80, 180, 255))
        glow_surf.set_alpha(50)
        for offset in [(-2, -2), (2, 2), (-2, 2), (2, -2)]:
            self.screen.blit(glow_surf, title_rect.move(offset))

        self.screen.blit(title_surf, title_rect)

        # Glowing Underline
        underline_y = title_rect.bottom + 8
        underline_w = title_rect.width + 60
        start_x = self.width // 2 - underline_w // 2

        for i, height in enumerate([3, 1]):
            alpha = 180 if i == 0 else 100
            color = (100, 200, 255, alpha)
            line_surf = pygame.Surface((underline_w, height), pygame.SRCALPHA)
            line_surf.fill(color)
            self.screen.blit(line_surf, (start_x, underline_y + i * 3))

        # Subtitle
        if self.game_mode == MODE_LOCAL_MULTIPLAYER:
            subtitle = "LOCAL MULTIPLAYER"
        else:
            subtitle = f"Selecting player {self.current_player + 1} of {self.num_players}"
        
        subtitle_surf = self._font_body.render(subtitle, True, SUBHEADER_COLOR)
        self.screen.blit(subtitle_surf, subtitle_surf.get_rect(center=(self.width // 2, 128)))

        # Hint text
        if self.game_mode == MODE_LOCAL_MULTIPLAYER:
             hint_text = f"Player {self.current_player + 1}: Click a character to preview their run"
        else:
             hint_text = self.mode_hint
        
        hint_surf = self._font_small.render(hint_text, True, MODE_HINT_COLOR)
        self.screen.blit(hint_surf, hint_surf.get_rect(center=(self.width // 2, 158)))

    def _draw_cards(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        self.hover_index = None
        current_time = pygame.time.get_ticks()

        for idx, card in enumerate(self.cards):
            char_name = card["name"]
            meta = CHARACTER_METADATA.get(char_name, {
                "color": (200, 200, 200),
                "ability": "Unknown Power",
                "icon": "?",
                "desc": "Standard ability",
            })
            base_color = meta["color"]

            rect = card["rect"]
            hovered = rect.collidepoint(mouse_pos)
            if hovered:
                self.hover_index = idx

            is_active = idx == self.active_index
            locked_slots = self._locked_slots_for(char_name)

            # --- Interactive State Logic ---
            scale = 1.0
            
            if locked_slots:
                # Pulse effect
                pulse = (math.sin(current_time * 0.005) + 1) * 0.5  # 0.0 to 1.0
                glow_int = int(100 + 155 * pulse)
                bg_color = (20, 20, 30, 240)
                border_color = (255, 255, 255) # White border for locked
                # Bright pulsing glow
                glow_color = (base_color[0], base_color[1], base_color[2], glow_int)
                border_width = 3
                scale = 1.02 # Slightly larger
            elif is_active:
                bg_color = (30, 35, 50, 250)
                border_color = base_color
                glow_color = (base_color[0], base_color[1], base_color[2], 120)
                border_width = 3
                scale = 1.05
            elif hovered:
                bg_color = (35, 40, 60, 250)
                # Brighten border
                border_color = tuple(min(255, c + 40) for c in base_color)
                glow_color = (base_color[0], base_color[1], base_color[2], 100)
                border_width = 2
                scale = 1.05
            else:
                bg_color = (16, 20, 35, 220)
                border_color = (60, 70, 90)
                glow_color = None
                border_width = 2
            
            # Apply Scale
            if scale != 1.0:
                w = int(rect.width * scale)
                h = int(rect.height * scale)
                draw_rect = pygame.Rect(0, 0, w, h)
                draw_rect.center = rect.center
            else:
                draw_rect = rect.copy()

            # --- Drawing ---

            # 1. Glow
            if glow_color:
                glow_rect = draw_rect.inflate(14, 14)
                glow_surf = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                _draw_rounded_rect(glow_surf, glow_surf.get_rect(), (0,0,0,0), glow_color, 6, CARD_RADIUS + 6)
                self.screen.blit(glow_surf, glow_rect.topleft, special_flags=pygame.BLEND_ADD)

            # 2. Main Card Body
            _draw_rounded_rect(self.screen, draw_rect, bg_color, border_color, border_width, CARD_RADIUS)

            # 3. Inner Stage
            stage_height = int(draw_rect.height * 0.55)
            stage_rect = pygame.Rect(draw_rect.x + 8, draw_rect.y + 8, draw_rect.width - 16, stage_height)
            stage_color = (10, 12, 20, 150)
            _draw_rounded_rect(self.screen, stage_rect, stage_color, (0,0,0,0), 0, CARD_RADIUS - 4)

            # 4. Character Sprite
            animation = card["animations"][card["current_state"]]
            frame = animation.image
            # Scale frame if card is scaled?
            if scale != 1.0:
                fw = int(frame.get_width() * scale)
                fh = int(frame.get_height() * scale)
                frame = pygame.transform.scale(frame, (fw, fh))
            
            frame_rect = frame.get_rect(midbottom=(stage_rect.centerx, stage_rect.bottom - 20))
            
            # Shadow
            shadow_width = frame_rect.width * 0.7
            if shadow_width > 0:
                shadow_rect = pygame.Rect(0, 0, shadow_width, 14 * scale)
                shadow_rect.center = (frame_rect.centerx, frame_rect.bottom - 4 * scale)
                shadow_surf = pygame.Surface(shadow_rect.size, pygame.SRCALPHA)
                pygame.draw.ellipse(shadow_surf, (0, 0, 0, 80), ((0,0), shadow_rect.size))
                self.screen.blit(shadow_surf, shadow_rect.topleft)

            self.screen.blit(frame, frame_rect)

            # 5. Info Section
            info_y_start = stage_rect.bottom + 12 * scale
            
            # Name
            name_surf = self._font_body.render(char_name.upper(), True, (255, 255, 255))
            name_rect = name_surf.get_rect(midtop=(draw_rect.centerx, info_y_start))
            self.screen.blit(name_surf, name_rect)

            # Ability Badge
            ability_text = f"{meta['icon']} {meta['ability']}"
            badge_surf = self._font_small.render(ability_text, True, (255, 255, 255))
            badge_w = badge_surf.get_width() + 24
            badge_h = badge_surf.get_height() + 10
            badge_rect = pygame.Rect(0, 0, badge_w, badge_h)
            badge_rect.midtop = (draw_rect.centerx, name_rect.bottom + 10 * scale)
            
            badge_bg_color = (base_color[0], base_color[1], base_color[2], 200)
            _draw_rounded_rect(self.screen, badge_rect, badge_bg_color, base_color, 1, 12)
            self.screen.blit(badge_surf, badge_surf.get_rect(center=badge_rect.center))

            # Description (Only show if NOT locked, to avoid clutter)
            if not locked_slots:
                desc_y = badge_rect.bottom + 12 * scale
                desc_lines = meta["desc"].split('\n')
                for line in desc_lines:
                    line_surf = self._font_small.render(line, True, (180, 190, 200))
                    line_rect = line_surf.get_rect(midtop=(draw_rect.centerx, desc_y))
                    self.screen.blit(line_surf, line_rect)
                    desc_y += 20 * scale

            # 6. Locked Banner / State
            if locked_slots:
                # Dim background
                dim_surf = pygame.Surface(draw_rect.size, pygame.SRCALPHA)
                dim_surf.fill((0, 0, 0, 120))
                self.screen.blit(dim_surf, draw_rect.topleft)

                # Banner
                banner_height = 50 * scale
                banner_rect = pygame.Rect(0, 0, draw_rect.width + 20, banner_height)
                banner_rect.center = draw_rect.center
                
                # Dynamic banner color
                banner_color = (base_color[0], base_color[1], base_color[2], 230)
                
                # Draw Banner
                pygame.draw.rect(self.screen, banner_color, banner_rect, border_radius=4)
                pygame.draw.rect(self.screen, (255, 255, 255), banner_rect, 2, border_radius=4)

                # Text
                players_text = " & ".join([f"P{i+1}" for i in locked_slots])
                full_text = f"{players_text} LOCKED IN"

                text_surf = self._font_heading.render(full_text, True, (255, 255, 255))
                # Adjust font size if too big
                if text_surf.get_width() > banner_rect.width - 20:
                     w = int(banner_rect.width - 30)
                     h = int(text_surf.get_height() * (w / text_surf.get_width()))
                     text_surf = pygame.transform.scale(text_surf, (w, h))
                
                text_rect = text_surf.get_rect(center=banner_rect.center)
                self.screen.blit(text_surf, text_rect)

    def _draw_summary(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        self._draw_buttons(mouse_pos)
        
        # Styled Tooltip Box
        if self.num_players == 1:
            instructions = "Click to preview • ENTER to Lock In"
        else:
            if self.current_player < self.num_players:
                instructions = f"Player {self.current_player + 1}: Select your hero"
            else:
                 instructions = "Ready to start!"

        text_surf = self._font_small.render(instructions, True, (200, 230, 255))
        
        # Background for tooltip
        bg_width = text_surf.get_width() + 50
        bg_height = 36
        bg_rect = pygame.Rect(0, 0, bg_width, bg_height)
        bg_rect.midbottom = (self.width // 2, self.height - 25)
        
        # Translucent dark pill shape
        s = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(s, (10, 15, 30, 200), s.get_rect(), border_radius=18)
        # Thin glowing border
        pygame.draw.rect(s, (60, 100, 140, 150), s.get_rect(), 1, border_radius=18)
        
        self.screen.blit(s, bg_rect.topleft)
        self.screen.blit(text_surf, text_surf.get_rect(center=bg_rect.center))

    def _draw_buttons(self, mouse_pos: tuple) -> None:
        # Back Button (simple style)
        back_hover = self._back_button_rect.collidepoint(mouse_pos)
        back_bg = (40, 50, 70) if back_hover else (30, 35, 50)
        _draw_rounded_rect(self.screen, self._back_button_rect, back_bg, (80, 90, 110), 1, BUTTON_RADIUS)
        back_text = self._font_body.render("BACK", True, (200, 200, 220))
        self.screen.blit(back_text, back_text.get_rect(center=self._back_button_rect.center))

        # Lock / Action Button (Glowing Styled)
        lock_enabled = self.active_index is not None and self.current_player < self.num_players
        lock_rect = self._lock_button_rect
        is_hover = lock_enabled and lock_rect.collidepoint(mouse_pos)
        
        if self.current_player >= self.num_players:
            # All selected? maybe change text to START? 
            # Logic says returns selection when num_players reached, so this state might be transient/last frame
            label = "START GAME"
            base_color = (80, 220, 100) # Green
        else:
            label = "SELECT HERO" # Changed from LOCK IN to generic action text or keep LOCK IN
            label = "CONFIRM"
            base_color = (255, 180, 40) # Gold/Amber default

            # Try to match active character color if possible
            if self.active_index is not None and 0 <= self.active_index < len(self.cards):
                char_name = self.cards[self.active_index]["name"]
                meta = CHARACTER_METADATA.get(char_name)
                if meta:
                    base_color = meta["color"]

        if not lock_enabled:
            # Disabled state
            _draw_rounded_rect(self.screen, lock_rect, (30, 30, 35), (60, 60, 70), 2, BUTTON_RADIUS)
            text_surf = self._font_body.render("SELECT HERO", True, (100, 100, 100))
            self.screen.blit(text_surf, text_surf.get_rect(center=lock_rect.center))
        else:
            # Active State
            # 1. Glow behind
            if is_hover:
                 glow_rect = lock_rect.inflate(16, 16)
                 s = pygame.Surface(glow_rect.size, pygame.SRCALPHA)
                 # Soft glow
                 pygame.draw.rect(s, (*base_color, 60), s.get_rect(), border_radius=BUTTON_RADIUS+8)
                 self.screen.blit(s, glow_rect.topleft, special_flags=pygame.BLEND_ADD)
            
            # 2. Button Body
            bg_color = (base_color[0]//4, base_color[1]//4, base_color[2]//4)
            if is_hover:
                bg_color = (base_color[0]//2, base_color[1]//2, base_color[2]//2)
            
            _draw_rounded_rect(self.screen, lock_rect, bg_color, base_color, 2, BUTTON_RADIUS)
            
            # 3. Text
            text_surf = self._font_body.render(label, True, (255, 255, 255))
            self.screen.blit(text_surf, text_surf.get_rect(center=lock_rect.center))

            # 4. Player Indicator Badge (Floating above)
            if self.current_player < self.num_players:
                p_idx = self.current_player + 1
                badge_radius = 18
                badge_center = (lock_rect.centerx, lock_rect.top - 10)
                
                # Badge Glow
                pygame.draw.circle(self.screen, (0, 0, 0, 100), badge_center, badge_radius + 2)
                
                # Badge Circle
                # Cycle colors or specific P1/P2 colors?
                # P1: Blue, P2: Red, P3: Green, P4: Yellow
                p_colors = [(60, 140, 255), (255, 60, 60), (60, 255, 100), (255, 220, 40)]
                p_color = p_colors[(p_idx - 1) % 4]
                
                pygame.draw.circle(self.screen, p_color, badge_center, badge_radius)
                pygame.draw.circle(self.screen, (255,255,255), badge_center, badge_radius, 2)
                
                # 'P1' Text
                p_text = self._font_heading.render(f"P{p_idx}", True, (255, 255, 255))
                # Scale down slightly
                ts = pygame.transform.scale(p_text, (int(p_text.get_width()*0.6), int(p_text.get_height()*0.6)))
                self.screen.blit(ts, ts.get_rect(center=badge_center))

    def _trigger_back(self) -> None:
        if self._closing:
            return
        self.back_requested = True
        self._closing = True
        self._fade(False)

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
        mouse_pos = pygame.mouse.get_pos()
        for idx, card in enumerate(self.cards):
            # Check mouse hover or active selection triggers run animation
            is_hovered = card["rect"].collidepoint(mouse_pos)
            is_active = (idx == self.active_index)
            
            desired_state = "run" if (is_active or is_hovered) else "idle"
            
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
                    self.quit_requested = True
                    return None
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._lock_button_rect.collidepoint(event.pos):
                        result = self._lock_current_selection()
                        if result is not None:
                            return result
                    elif self._back_button_rect.collidepoint(event.pos):
                        self._trigger_back()
                        return None
                    else:
                        for idx, card in enumerate(self.cards):
                            if card["rect"].collidepoint(event.pos):
                                self._set_active_index(idx)
                                break
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self._trigger_back()
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
