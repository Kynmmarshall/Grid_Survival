from __future__ import annotations

import math
from typing import Any

import pygame

from animation import SpriteAnimation, load_frames_from_directory
from character_manager import build_animation_paths
from scenes.common import draw_online_status_badge, update_online_status
from settings import (
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    FONT_PATH_SMALL,
    TARGET_FPS,
    WINDOW_SIZE,
)


def _load_font(path: str, size: int, bold: bool = False) -> pygame.font.Font:
    try:
        return pygame.font.Font(path, size)
    except (pygame.error, FileNotFoundError, OSError):
        try:
            return pygame.font.SysFont("consolas", size, bold=bold)
        except Exception:
            return pygame.font.Font(None, size)


def _draw_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    bg: tuple[int, int, int, int],
    border: tuple[int, int, int],
    border_width: int = 2,
    radius: int = 12,
) -> None:
    pane = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(pane, bg, pane.get_rect(), border_radius=radius)
    surface.blit(pane, rect.topleft)
    pygame.draw.rect(surface, border, rect, border_width, border_radius=radius)


class RRGainScreen:
    """Animated RR transition shown between rounds."""

    def __init__(self, username: str, rr_before: int, rr_after: int, title: str):
        self.username = username
        self.rr_before = int(rr_before)
        self.rr_after = int(rr_after)
        self.rr_delta = int(rr_after) - int(rr_before)
        self.title = title

        self._font_title = _load_font(FONT_PATH_HEADING, 34, bold=True)
        self._font_big = _load_font(FONT_PATH_HEADING, 56, bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, 24)
        self._font_small = _load_font(FONT_PATH_SMALL, 18)

        self._display_rr = float(self.rr_before)
        self._elapsed = 0.0
        self._done_hold = 0.0

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> str:
        while True:
            dt = clock.tick(TARGET_FPS) / 1000.0
            update_online_status(dt)
            self._update(dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return "menu"
                if event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_RETURN,
                    pygame.K_SPACE,
                ):
                    return "continue"

            self.draw(screen)
            pygame.display.flip()

            if self._done_hold >= 1.1:
                return "continue"

    def _update(self, dt: float) -> None:
        self._elapsed += dt
        duration = 1.8
        t = min(1.0, self._elapsed / duration)
        eased = 1.0 - pow(1.0 - t, 3)
        self._display_rr = self.rr_before + (self.rr_after - self.rr_before) * eased
        if t >= 1.0:
            self._done_hold += dt

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill((10, 12, 22))
        w, h = WINDOW_SIZE

        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        glow = int(40 + 20 * (0.5 + 0.5 * math.sin(self._elapsed * math.pi * 2.0)))
        pygame.draw.circle(overlay, (92, 175, 255, glow), (w // 2, h // 2 - 80), 240)
        screen.blit(overlay, (0, 0), special_flags=pygame.BLEND_ADD)

        panel = pygame.Rect(0, 0, min(760, w - 120), 360)
        panel.center = (w // 2, h // 2)
        _draw_panel(screen, panel, (16, 23, 38, 236), (110, 180, 255), 3, 18)

        title = self._font_title.render(self.title, True, (240, 245, 255))
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 56)))

        sub = self._font_body.render(f"Player: {self.username}", True, (190, 210, 240))
        screen.blit(sub, sub.get_rect(center=(panel.centerx, panel.top + 100)))

        rr_value = int(round(self._display_rr))
        rr_text = self._font_big.render(f"RR {rr_value}", True, (255, 225, 135))
        screen.blit(rr_text, rr_text.get_rect(center=(panel.centerx, panel.centery - 10)))

        delta_color = (90, 230, 130) if self.rr_delta >= 0 else (255, 115, 115)
        sign = "+" if self.rr_delta >= 0 else ""
        delta = self._font_title.render(f"{sign}{self.rr_delta} RR", True, delta_color)
        screen.blit(delta, delta.get_rect(center=(panel.centerx, panel.centery + 52)))

        hint = self._font_small.render("Press ENTER to skip", True, (170, 185, 210))
        screen.blit(hint, hint.get_rect(center=(panel.centerx, panel.bottom - 36)))
        draw_online_status_badge(
            screen,
            reserved_rects=(panel,),
            preferred_corners=("top-right", "bottom-right", "top-left", "bottom-left"),
        )


class MatchSummaryScreen:
    """Round/match summary screen with MVP and per-player stats."""

    def __init__(
        self,
        players: list[dict[str, Any]],
        mvp_username: str,
        title: str,
        allow_continue: bool,
    ):
        self.players = players
        self.mvp_username = mvp_username
        self.title = title
        self.allow_continue = bool(allow_continue)

        self._font_title = _load_font(FONT_PATH_HEADING, 30, bold=True)
        self._font_header = _load_font(FONT_PATH_BODY, 20, bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, 18)
        self._font_small = _load_font(FONT_PATH_SMALL, 16)

        self._anims: list[SpriteAnimation | None] = []
        self._placeholder_frames: list[pygame.Surface] = []
        self._menu_rect = pygame.Rect(0, 0, 190, 48)
        self._continue_rect = pygame.Rect(0, 0, 190, 48)

        for row in self.players:
            self._anims.append(self._load_idle_animation(str(row.get("character", "Caveman"))))

    def run(self, screen: pygame.Surface, clock: pygame.time.Clock) -> str:
        while True:
            dt = clock.tick(TARGET_FPS) / 1000.0
            update_online_status(dt)
            for anim in self._anims:
                if anim is not None:
                    anim.update(dt)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return "quit"
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return "menu"
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if self.allow_continue:
                        return "continue"
                    return "menu"
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._menu_rect.collidepoint(event.pos):
                        return "menu"
                    if self.allow_continue and self._continue_rect.collidepoint(event.pos):
                        return "continue"

            self.draw(screen)
            pygame.display.flip()

    def _load_idle_animation(self, character_name: str) -> SpriteAnimation | None:
        try:
            paths = build_animation_paths(character_name)
            idle_dir = paths.get("idle", {}).get("down")
            if idle_dir is None:
                return None
            frames = load_frames_from_directory(idle_dir, scale=0.22)
            if not frames:
                return None
            return SpriteAnimation(frames, frame_duration=1 / 10, loop=True)
        except Exception:
            return None

    def _fallback_frame(self) -> pygame.Surface:
        if self._placeholder_frames:
            return self._placeholder_frames[0]
        surf = pygame.Surface((54, 54), pygame.SRCALPHA)
        pygame.draw.rect(surf, (80, 100, 140), surf.get_rect(), border_radius=8)
        pygame.draw.rect(surf, (190, 210, 245), surf.get_rect(), 2, border_radius=8)
        self._placeholder_frames.append(surf)
        return surf

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill((8, 12, 24))
        w, h = WINDOW_SIZE

        panel = pygame.Rect(0, 0, min(1100, w - 80), min(670, h - 70))
        panel.center = (w // 2, h // 2)
        _draw_panel(screen, panel, (12, 18, 33, 238), (124, 170, 255), 3, 16)

        title = self._font_title.render(self.title, True, (245, 248, 255))
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 42)))

        mvp = self._font_header.render(f"MVP: {self.mvp_username}", True, (255, 220, 120))
        screen.blit(mvp, mvp.get_rect(center=(panel.centerx, panel.top + 80)))

        table = pygame.Rect(panel.left + 28, panel.top + 112, panel.width - 56, panel.height - 208)
        _draw_panel(screen, table, (20, 28, 48, 220), (92, 126, 180), 2, 12)

        # Header and row values share the same anchors so every column lines up.
        header_ref_rect = pygame.Rect(table.left + 12, table.top + 46, table.width - 24, 64)
        text_left = header_ref_rect.left + 80
        text_right = header_ref_rect.right - 22
        span = max(300, text_right - text_left)

        x_player = text_left
        x_char = text_left + int(span * 0.24)
        x_rounds = text_left + int(span * 0.53)
        x_kd = text_left + int(span * 0.66)
        x_dmg_dealt = text_left + int(span * 0.79)
        x_dmg_taken = text_left + int(span * 0.92)

        header_y = table.top + 16
        header_color = (176, 200, 235)
        player_header = self._font_small.render("PLAYER", True, header_color)
        char_header = self._font_small.render("CHAR", True, header_color)
        rounds_header = self._font_small.render("ROUNDS", True, header_color)
        kd_header = self._font_small.render("K/D", True, header_color)
        dealt_header = self._font_small.render("DMG DEALT", True, header_color)
        taken_header = self._font_small.render("DMG TAKEN", True, header_color)

        screen.blit(player_header, player_header.get_rect(topleft=(x_player, header_y)))
        screen.blit(char_header, char_header.get_rect(topleft=(x_char, header_y)))
        screen.blit(rounds_header, rounds_header.get_rect(midtop=(x_rounds, header_y)))
        screen.blit(kd_header, kd_header.get_rect(midtop=(x_kd, header_y)))
        screen.blit(dealt_header, dealt_header.get_rect(midtop=(x_dmg_dealt, header_y)))
        screen.blit(taken_header, taken_header.get_rect(midtop=(x_dmg_taken, header_y)))

        row_y = table.top + 46
        row_h = 64
        for idx, row in enumerate(self.players):
            row_rect = pygame.Rect(table.left + 12, row_y, table.width - 24, row_h)
            is_mvp = str(row.get("username", "")) == self.mvp_username
            base = (42, 58, 90, 225) if is_mvp else (26, 38, 66, 215)
            border = (255, 215, 135) if is_mvp else (98, 128, 182)
            _draw_panel(screen, row_rect, base, border, 2, 10)

            anim = self._anims[idx] if idx < len(self._anims) else None
            frame = anim.image if anim is not None else self._fallback_frame()
            frame_rect = frame.get_rect(center=(row_rect.left + 38, row_rect.centery + 6))
            screen.blit(frame, frame_rect)

            username = str(row.get("username", "-"))[:14]
            character = str(row.get("character", "-"))[:14]
            rounds_won = int(row.get("rounds_won", 0))
            eliminations = int(row.get("eliminations", 0))
            deaths = int(row.get("deaths", 0))
            dmg_dealt = int(row.get("damage_dealt", 0))
            dmg_taken = int(row.get("damage_taken", 0))

            name_text = self._font_body.render(username, True, (240, 245, 255))
            char_text = self._font_body.render(character, True, (195, 220, 250))
            rounds_text = self._font_body.render(str(rounds_won), True, (230, 236, 250))
            kd_text = self._font_body.render(f"{eliminations}/{deaths}", True, (230, 236, 250))
            dealt_text = self._font_body.render(str(dmg_dealt), True, (230, 236, 250))
            taken_text = self._font_body.render(str(dmg_taken), True, (230, 236, 250))

            screen.blit(name_text, name_text.get_rect(midleft=(x_player, row_rect.centery - 2)))
            screen.blit(char_text, char_text.get_rect(midleft=(x_char, row_rect.centery - 2)))
            screen.blit(rounds_text, rounds_text.get_rect(center=(x_rounds, row_rect.centery - 2)))
            screen.blit(kd_text, kd_text.get_rect(center=(x_kd, row_rect.centery - 2)))
            screen.blit(dealt_text, dealt_text.get_rect(center=(x_dmg_dealt, row_rect.centery - 2)))
            screen.blit(taken_text, taken_text.get_rect(center=(x_dmg_taken, row_rect.centery - 2)))

            row_y += row_h + 10
            if row_y + row_h > table.bottom:
                break

        self._menu_rect.size = (210, 50)
        self._menu_rect.center = (panel.centerx + 132, panel.bottom - 52)
        self._draw_button(screen, self._menu_rect, "MAIN MENU", (135, 85, 80), (245, 210, 205))

        if self.allow_continue:
            self._continue_rect.size = (210, 50)
            self._continue_rect.center = (panel.centerx - 132, panel.bottom - 52)
            self._draw_button(screen, self._continue_rect, "CONTINUE", (76, 124, 86), (208, 240, 215))
        else:
            hint = self._font_small.render("Match complete. Return to menu.", True, (180, 195, 222))
            screen.blit(hint, hint.get_rect(center=(panel.centerx - 132, panel.bottom - 52)))

        draw_online_status_badge(
            screen,
            reserved_rects=(panel,),
            preferred_corners=("top-right", "bottom-right", "top-left", "bottom-left"),
        )

    def _draw_button(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        color: tuple[int, int, int],
        text_color: tuple[int, int, int],
    ) -> None:
        hovered = rect.collidepoint(pygame.mouse.get_pos())
        bg = (
            min(255, color[0] + 18),
            min(255, color[1] + 18),
            min(255, color[2] + 18),
            235,
        ) if hovered else (*color, 225)
        border = (245, 245, 250) if hovered else (185, 198, 218)
        _draw_panel(screen, rect, bg, border, 2, 10)
        txt = self._font_small.render(label, True, text_color)
        screen.blit(txt, txt.get_rect(center=rect.center))
