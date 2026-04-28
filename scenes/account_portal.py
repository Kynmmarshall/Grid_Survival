from __future__ import annotations

import threading

import pygame

from backend.account_service import AccountProfile, AccountService
from settings import (
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    FONT_PATH_SMALL,
    FONT_SIZE_BODY,
    FONT_SIZE_HEADING,
    FONT_SIZE_SMALL,
    SCENE_FADE_SPEED,
    SCENE_OVERLAY_COLOR,
    TARGET_FPS,
    WINDOW_SIZE,
)
from .common import (
    SceneAudioOverlay,
    _draw_rounded_rect,
    _load_font,
    set_menu_sync_indicator_result,
    set_menu_sync_indicator_running,
)
from .title_screen import TitleScreen


class AccountPortalScreen:
    """Account/login/profile/leaderboard hub shown before mode selection."""

    def __init__(
        self,
        screen: pygame.Surface,
        clock: pygame.time.Clock,
        service: AccountService,
        suggested_username: str,
        current_username: str | None = None,
    ):
        self.screen = screen
        self.clock = clock
        self.service = service
        self.width, self.height = WINDOW_SIZE

        self.current_username = (current_username or "").strip() or None
        self._suggested_username = (suggested_username or "Player").strip() or "Player"
        self.message = ""
        self.message_color = (220, 220, 235)

        self._state = "menu"  # menu | login | register | profile | leaderboard
        self._focus = "username"
        self._username_input = self.current_username or self._suggested_username
        self._password_input = ""
        self._switching_account = False
        self._switch_from_username: str | None = None

        self._profile_cache: AccountProfile | None = None
        self._leaderboard_cache: list[dict] = []
        self._leaderboard_online = False
        self._profile_view_mode = "ranked"
        self._leaderboard_view_mode = "ranked"
        self._leaderboard_selected_username: str | None = self.current_username
        self._leaderboard_row_hitboxes: list[tuple[pygame.Rect, str]] = []
        self._leaderboard_scroll_index = 0
        self._leaderboard_rows_per_page = 8

        self._font_title = _load_font(FONT_PATH_HEADING, max(34, FONT_SIZE_HEADING + 8), bold=True)
        self._font_welcome = _load_font(FONT_PATH_HEADING, max(36, FONT_SIZE_HEADING + 6), bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, max(20, FONT_SIZE_BODY - 2))
        self._font_small = _load_font(FONT_PATH_SMALL, max(16, FONT_SIZE_SMALL))
        self._font_tiny = _load_font(FONT_PATH_SMALL, max(14, FONT_SIZE_SMALL - 2))
        self._font_profile_label = _load_font(FONT_PATH_BODY, max(22, FONT_SIZE_BODY + 2), bold=True)
        self._font_profile_value = _load_font(FONT_PATH_BODY, max(22, FONT_SIZE_BODY + 2))
        self._font_profile_icon = _load_font(FONT_PATH_SMALL, max(14, FONT_SIZE_SMALL), bold=True)
        self._font_lb_title = _load_font(FONT_PATH_HEADING, max(30, FONT_SIZE_HEADING), bold=True)
        self._font_lb_header = _load_font(FONT_PATH_BODY, max(20, FONT_SIZE_BODY))
        self._font_lb_row = _load_font(FONT_PATH_BODY, max(19, FONT_SIZE_BODY - 1))
        self._font_lb_meta = _load_font(FONT_PATH_SMALL, max(16, FONT_SIZE_SMALL))
        self._font_lb_detail_title = _load_font(FONT_PATH_HEADING, max(28, FONT_SIZE_HEADING - 1), bold=True)
        self._font_lb_detail_label = _load_font(FONT_PATH_BODY, max(18, FONT_SIZE_BODY - 1), bold=True)
        self._font_lb_detail_value = _load_font(FONT_PATH_BODY, max(21, FONT_SIZE_BODY + 1))
        self._font_lb_detail_icon = _load_font(FONT_PATH_SMALL, max(14, FONT_SIZE_SMALL), bold=True)
        self._audio_overlay = SceneAudioOverlay(show_online_status=False)
        self._title_shell = TitleScreen(
            screen,
            clock,
            start_music=False,
            enable_tutorial_prompt=False,
        )
        self._wide_layout = self.width >= 1220

        self._button_rects: dict[str, pygame.Rect] = {}
        self._tutorial_button_rect = pygame.Rect(24, self.height - 124, 190, 46)
        self._controls_button_rect = pygame.Rect(self.width - 134, self.height - 68, 110, 46)
        self._auth_username_rect = pygame.Rect(0, 0, 0, 0)
        self._auth_password_rect = pygame.Rect(0, 0, 0, 0)
        self._auth_popup_visible = False
        self._auth_popup_title = ""
        self._auth_popup_lines: list[str] = []
        self._auth_popup_action = "info"
        self._auth_popup_primary_label = "OK"
        self._auth_popup_secondary_label: str | None = None
        self._auth_popup_primary_rect = pygame.Rect(0, 0, 0, 0)
        self._auth_popup_secondary_rect = pygame.Rect(0, 0, 0, 0)

        self._remote_online: bool | None = None
        self._remote_check_interval = 4.0
        self._remote_check_timer = self._remote_check_interval
        self._remote_check_running = False
        self._remote_check_result: bool | None = None
        self._request_remote_status_check(force=True)

    def run(self) -> dict[str, str | None]:
        self._fade("in")
        while True:
            dt = self.clock.tick(TARGET_FPS) / 1000.0
            self._update_title_shell(dt)
            self._update_remote_status(dt)

            for event in pygame.event.get():
                if self._audio_overlay.handle_event(event):
                    continue
                if event.type == pygame.QUIT:
                    return {"action": "quit", "player_name": None, "account_username": None}

                if self._auth_popup_visible and self._state in {"login", "register"}:
                    self._handle_auth_popup_event(event)
                    continue

                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self._tutorial_button_rect.collidepoint(event.pos):
                        self._open_tutorial_from_title()
                        continue
                    if self._controls_button_rect.collidepoint(event.pos):
                        self._open_controls_editor_from_title()
                        continue

                if self._state in {"login", "register"}:
                    result = self._handle_auth_event(event)
                    if result:
                        return result
                elif self._state == "menu":
                    result = self._handle_menu_event(event)
                    if result:
                        return result
                elif self._state == "profile":
                    result = self._handle_profile_event(event)
                    if result:
                        return result
                elif self._state == "leaderboard":
                    result = self._handle_leaderboard_event(event)
                    if result:
                        return result

            self._draw()
            pygame.display.flip()

    def _update_title_shell(self, dt: float) -> None:
        self._title_shell._title_time += dt
        self._title_shell._update_shake(dt)
        self._title_shell._update_particles(dt)

    def _draw_title_backdrop(self) -> None:
        self._title_shell._draw_background()
        self._title_shell._draw_title()

        dimmer = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        dimmer.fill((0, 0, 0, 95))
        self.screen.blit(dimmer, (0, 0))

    def _draw(self) -> None:
        self._button_rects.clear()
        self._leaderboard_row_hitboxes = []
        self._draw_title_backdrop()

        panel_height = min(650, self.height - 80)
        if self._state == "leaderboard":
            panel_width = min(760, max(520, self.width - 420))
            panel = pygame.Rect(24, 0, panel_width, panel_height)
            panel.centery = 20 + self.height // 2
        else:
            panel_width = min(760, max(560, self.width - 520)) if self._wide_layout else min(960, self.width - 100)
            panel = pygame.Rect(0, 0, panel_width, panel_height)
            panel.center = (self.width // 2, 20 + self.height // 2)

        border = (120, 170, 255) if self._state in {"leaderboard", "profile"} else (130, 220, 170)
        _draw_rounded_rect(self.screen, panel, (14, 18, 34, 230), border, 3, 18)

        title_text = {
            "menu": "ACCOUNT PORTAL",
            "login": "LOGIN",
            "register": "CREATE ACCOUNT",
            "profile": "PROFILE",
            "leaderboard": "LEADERBOARD",
        }.get(self._state, "ACCOUNT")

        title = self._font_title.render(title_text, True, (245, 245, 255))
        self.screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 48)))

        if self._state == "menu":
            self._draw_menu(panel)
        elif self._state in {"login", "register"}:
            self._draw_auth(panel)
        elif self._state == "profile":
            self._draw_profile(panel)
        elif self._state == "leaderboard":
            self._draw_leaderboard(panel)

        if self.message:
            msg = self._font_small.render(self.message, True, self.message_color)
            self.screen.blit(msg, msg.get_rect(center=(panel.centerx, panel.bottom - 26)))

        self._title_shell._draw_controls_panel()
        self._draw_controls_edit_button()
        self._draw_tutorial_button()
        self._draw_remote_status_badge()
        self._audio_overlay.draw(self.screen)
        self._draw_auth_popup()

    def _request_remote_status_check(self, force: bool = False) -> None:
        if self._remote_check_running:
            return
        if not force and self._remote_check_timer < self._remote_check_interval:
            return

        self._remote_check_timer = 0.0
        self._remote_check_running = True

        def _worker() -> None:
            status = False
            try:
                status = bool(self.service.is_remote_online())
            except Exception:
                status = False
            self._remote_check_result = status
            self._remote_check_running = False

        threading.Thread(target=_worker, daemon=True).start()

    def _update_remote_status(self, dt: float) -> None:
        self._remote_check_timer += max(0.0, float(dt))

        if self._remote_check_result is not None:
            self._remote_online = bool(self._remote_check_result)
            self._remote_check_result = None

        if self._remote_online is None and not self._remote_check_running:
            self._request_remote_status_check(force=True)
            return

        if self._remote_check_timer >= self._remote_check_interval:
            self._request_remote_status_check(force=False)

    def _draw_remote_status_badge(self) -> None:
        badge = pygame.Rect(0, 0, 212, 40)
        badge.topright = (self.width - 18, 18)

        if self._remote_online is None:
            label = "CHECKING STATUS"
            bg = (72, 72, 52, 220)
            border = (220, 196, 120)
            dot_color = (248, 218, 130)
        elif self._remote_online:
            label = "ONLINE MODE"
            if self._remote_check_running:
                label = "ONLINE MODE *"
            bg = (34, 78, 52, 220)
            border = (128, 224, 174)
            dot_color = (130, 244, 178)
        else:
            label = "OFFLINE MODE"
            if self._remote_check_running:
                label = "OFFLINE MODE *"
            bg = (86, 42, 42, 220)
            border = (236, 154, 154)
            dot_color = (255, 168, 168)

        _draw_rounded_rect(self.screen, badge, bg, border, 2, 12)
        dot_center = (badge.left + 20, badge.centery)
        pygame.draw.circle(self.screen, dot_color, dot_center, 6)

        label_surf = self._font_tiny.render(label, True, (244, 248, 255))
        self.screen.blit(label_surf, label_surf.get_rect(midleft=(badge.left + 34, badge.centery)))

    def _wrap_text(self, font: pygame.font.Font, text: str, max_width: int) -> list[str]:
        words = str(text).split()
        if not words:
            return [""]

        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    def _set_auth_popup(
        self,
        *,
        title: str,
        lines: list[str],
        action: str = "info",
        primary_label: str = "OK",
        secondary_label: str | None = None,
    ) -> None:
        self._auth_popup_visible = True
        self._auth_popup_title = str(title)
        self._auth_popup_lines = [str(line) for line in lines if str(line).strip()]
        self._auth_popup_action = str(action)
        self._auth_popup_primary_label = str(primary_label)
        self._auth_popup_secondary_label = str(secondary_label) if secondary_label else None

    def _clear_auth_popup(self) -> None:
        self._auth_popup_visible = False
        self._auth_popup_title = ""
        self._auth_popup_lines = []
        self._auth_popup_action = "info"
        self._auth_popup_primary_label = "OK"
        self._auth_popup_secondary_label = None
        self._auth_popup_primary_rect = pygame.Rect(0, 0, 0, 0)
        self._auth_popup_secondary_rect = pygame.Rect(0, 0, 0, 0)

    def _draw_auth_popup(self) -> None:
        if not self._auth_popup_visible:
            return

        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 182))
        self.screen.blit(overlay, (0, 0))

        popup = pygame.Rect(0, 0, min(680, self.width - 120), min(320, self.height - 160))
        popup.center = (self.width // 2, self.height // 2 + 8)
        _draw_rounded_rect(self.screen, popup, (16, 24, 44, 236), (126, 172, 235), 3, 16)

        title = self._font_profile_label.render(self._auth_popup_title or "NOTICE", True, (242, 247, 255))
        self.screen.blit(title, title.get_rect(center=(popup.centerx, popup.top + 40)))

        max_text_w = popup.width - 64
        line_y = popup.top + 82
        for raw_line in self._auth_popup_lines:
            for wrapped in self._wrap_text(self._font_small, raw_line, max_text_w):
                line_surf = self._font_small.render(wrapped, True, (206, 222, 246))
                self.screen.blit(line_surf, line_surf.get_rect(center=(popup.centerx, line_y)))
                line_y += 24

        btn_y = popup.bottom - 52
        if self._auth_popup_secondary_label:
            self._auth_popup_primary_rect = pygame.Rect(0, 0, 180, 44)
            self._auth_popup_secondary_rect = pygame.Rect(0, 0, 180, 44)
            self._auth_popup_primary_rect.center = (popup.centerx - 102, btn_y)
            self._auth_popup_secondary_rect.center = (popup.centerx + 102, btn_y)

            _draw_rounded_rect(
                self.screen,
                self._auth_popup_primary_rect,
                (70, 136, 102, 235),
                (194, 236, 204),
                2,
                10,
            )
            _draw_rounded_rect(
                self.screen,
                self._auth_popup_secondary_rect,
                (74, 94, 130, 235),
                (186, 204, 234),
                2,
                10,
            )
            primary = self._font_small.render(self._auth_popup_primary_label, True, (248, 252, 250))
            secondary = self._font_small.render(self._auth_popup_secondary_label, True, (244, 248, 255))
            self.screen.blit(primary, primary.get_rect(center=self._auth_popup_primary_rect.center))
            self.screen.blit(secondary, secondary.get_rect(center=self._auth_popup_secondary_rect.center))
        else:
            self._auth_popup_primary_rect = pygame.Rect(0, 0, 210, 44)
            self._auth_popup_primary_rect.center = (popup.centerx, btn_y)
            self._auth_popup_secondary_rect = pygame.Rect(0, 0, 0, 0)
            _draw_rounded_rect(
                self.screen,
                self._auth_popup_primary_rect,
                (70, 136, 102, 235),
                (194, 236, 204),
                2,
                10,
            )
            primary = self._font_small.render(self._auth_popup_primary_label, True, (248, 252, 250))
            self.screen.blit(primary, primary.get_rect(center=self._auth_popup_primary_rect.center))

    def _activate_auth_popup_primary(self) -> None:
        action = self._auth_popup_action
        if action == "register":
            self._state = "register"
            self._focus = "username"
            self._password_input = ""
            self.message = "Create a new account to continue."
            self.message_color = (190, 220, 255)
        self._clear_auth_popup()

    def _activate_auth_popup_secondary(self) -> None:
        self._clear_auth_popup()

    def _handle_auth_popup_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                self._activate_auth_popup_secondary()
                return
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._activate_auth_popup_primary()
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._auth_popup_primary_rect.collidepoint(event.pos):
                self._activate_auth_popup_primary()
                return
            if self._auth_popup_secondary_label and self._auth_popup_secondary_rect.collidepoint(event.pos):
                self._activate_auth_popup_secondary()
                return

    def _show_login_guidance_popup(self, message: str) -> None:
        text = str(message).strip().lower()
        if "not found on local or online server" in text:
            self._set_auth_popup(
                title="ACCOUNT NOT FOUND",
                lines=[
                    "No account was found locally or on the online server.",
                    "Please register a new account to continue.",
                ],
                action="register",
                primary_label="REGISTER",
                secondary_label="BACK",
            )
            return

        if "connect to internet" in text and "local" in text:
            self._set_auth_popup(
                title="ONLINE ACCOUNT CHECK",
                lines=[
                    "This account was not found in your local database.",
                    "Connect to internet and press LOGIN again",
                    "to check if you have this account online.",
                ],
                action="connect",
                primary_label="OK",
            )
            return

        if "online check failed" in text:
            self._set_auth_popup(
                title="CONNECTION REQUIRED",
                lines=[
                    "The online account check failed.",
                    "Connect to internet and try LOGIN again.",
                ],
                action="connect",
                primary_label="OK",
            )

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

    def _draw_controls_edit_button(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        hovered = self._controls_button_rect.collidepoint(mouse_pos)
        base_color = (30, 55, 80, 210)
        hover_color = (60, 100, 140, 230)
        bg_color = hover_color if hovered else base_color
        border_color = (100, 160, 220)
        _draw_rounded_rect(self.screen, self._controls_button_rect, bg_color, border_color, 2, 14)
        label = self._font_small.render("EDIT", True, (235, 240, 250))
        self.screen.blit(label, label.get_rect(center=self._controls_button_rect.center))

    def _draw_button(
        self,
        panel: pygame.Rect,
        key: str,
        label: str,
        row: int,
        *,
        color: tuple[int, int, int] = (70, 110, 170),
        width: int = 330,
    ) -> pygame.Rect:
        rect = pygame.Rect(0, 0, width, 48)
        rect.center = (panel.centerx, panel.top + 160 + row * 60)
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse)

        bg = (
            min(255, color[0] + 20),
            min(255, color[1] + 20),
            min(255, color[2] + 20),
            240,
        ) if hovered else (*color, 230)
        border = (225, 235, 255) if hovered else (150, 185, 220)

        _draw_rounded_rect(self.screen, rect, bg, border, 2, 12)
        text = self._font_small.render(label, True, (250, 250, 255))
        self.screen.blit(text, text.get_rect(center=rect.center))

        self._button_rects[key] = rect
        return rect

    def _draw_menu(self, panel: pygame.Rect) -> None:
        who = self.current_username or ""
        row = 1
        if self.current_username:
            info = self._font_welcome.render(f"Welcome, {who}", True, (245, 245, 255))
            
            self.screen.blit(info, info.get_rect(center=(panel.centerx, panel.top + 116)))

            self._draw_button(panel, "continue_account", "CONTINUE TO GAME", row, color=(75, 145, 95))
            row += 1
            self._draw_button(panel, "profile", "PROFILE", row)
            row += 1
            self._draw_button(panel, "switch", "SWITCH ACCOUNT", row, color=(145, 110, 80))
            row += 1
            self._draw_button(panel, "leaderboard", "LEADERBOARD (ONLINE)", row, color=(86, 122, 190))
            row += 1
            self._draw_button(panel, "back", "BACK", row, color=(95, 95, 110))
        else:
            if self._switching_account and self._switch_from_username:
                info = self._font_small.render("Switch account mode", True, (195, 215, 245))
                hint = self._font_tiny.render(
                    "Login/create another account, or BACK to cancel switch.",
                    True,
                    (170, 190, 220),
                )
            else:
                info = self._font_small.render("No active account", True, (195, 215, 245))
                hint = self._font_tiny.render(
                    "Login or create an account to continue.",
                    True,
                    (170, 190, 220),
                )
            self.screen.blit(info, info.get_rect(center=(panel.centerx, panel.top + 118)))
            self.screen.blit(hint, hint.get_rect(center=(panel.centerx, panel.top + 142)))

            self._draw_button(panel, "login", "LOGIN", row)
            row += 1
            self._draw_button(panel, "register", "CREATE ACCOUNT", row, color=(95, 130, 170))
            row += 1

            self._draw_button(panel, "leaderboard", "LEADERBOARD (ONLINE)", row, color=(86, 122, 190))
            row += 1
            back_label = "CANCEL SWITCH" if self._switching_account and self._switch_from_username else "BACK"
            self._draw_button(panel, "back", back_label, row, color=(95, 95, 110))

    def _cancel_switch_account(self) -> bool:
        if not self._switching_account:
            return False
        if not self._switch_from_username:
            self._switching_account = False
            return False

        self.current_username = self._switch_from_username
        self._profile_cache = self.service.get_profile(self.current_username)
        self._username_input = self.current_username
        self._password_input = ""
        self._switch_from_username = None
        self._switching_account = False
        self._state = "menu"
        self.message = "Switch account cancelled."
        self.message_color = (190, 220, 255)
        return True

    def _draw_auth(self, panel: pygame.Rect) -> None:
        mode_label = "Create a new account" if self._state == "register" else "Sign in to existing account"
        line = self._font_small.render(mode_label, True, (198, 214, 240))
        self.screen.blit(line, line.get_rect(center=(panel.centerx, panel.top + 118)))

        user_rect = pygame.Rect(0, 0, 420, 50)
        pass_rect = pygame.Rect(0, 0, 420, 50)
        user_rect.center = (panel.centerx, panel.top + 206)
        pass_rect.center = (panel.centerx, panel.top + 276)
        self._auth_username_rect = user_rect.copy()
        self._auth_password_rect = pass_rect.copy()

        self._draw_input_box(user_rect, "USERNAME", self._username_input, self._focus == "username")
        self._draw_input_box(pass_rect, "PASSWORD", "*" * len(self._password_input), self._focus == "password")

        self._button_rects["submit"] = pygame.Rect(0, 0, 200, 48)
        self._button_rects["submit"].center = (panel.centerx - 110, panel.top + 356)
        _draw_rounded_rect(self.screen, self._button_rects["submit"], (72, 140, 96, 230), (200, 235, 210), 2, 10)
        submit_label = "CREATE" if self._state == "register" else "LOGIN"
        submit_txt = self._font_small.render(submit_label, True, (248, 252, 250))
        self.screen.blit(submit_txt, submit_txt.get_rect(center=self._button_rects["submit"].center))

        self._button_rects["cancel"] = pygame.Rect(0, 0, 200, 48)
        self._button_rects["cancel"].center = (panel.centerx + 110, panel.top + 356)
        _draw_rounded_rect(self.screen, self._button_rects["cancel"], (96, 96, 118, 230), (205, 208, 232), 2, 10)
        cancel_txt = self._font_small.render("BACK", True, (246, 247, 255))
        self.screen.blit(cancel_txt, cancel_txt.get_rect(center=self._button_rects["cancel"].center))

        hint = self._font_tiny.render("Click a field or TAB to switch. ENTER submits.", True, (170, 185, 214))
        self.screen.blit(hint, hint.get_rect(center=(panel.centerx, panel.top + 412)))

    def _draw_input_box(self, rect: pygame.Rect, label: str, value: str, focused: bool) -> None:
        bg = (24, 30, 48, 232)
        border = (120, 190, 255) if focused else (110, 130, 165)
        _draw_rounded_rect(self.screen, rect, bg, border, 2, 10)

        label_surf = self._font_tiny.render(label, True, (150, 176, 220))
        self.screen.blit(label_surf, (rect.left + 12, rect.top - 18))

        text = value if value else ""
        cursor_visible = bool(focused and (pygame.time.get_ticks() // 450) % 2 == 0)
        cursor_w = 8 if cursor_visible else 0
        max_text_w = max(20, rect.width - 24 - cursor_w)
        display_text = self._fit_input_text(text, max_text_w)

        text_surf = self._font_small.render(display_text, True, (245, 248, 255))
        text_pos = (rect.left + 12, rect.centery - text_surf.get_height() // 2)
        self.screen.blit(text_surf, text_pos)

        if cursor_visible:
            cursor_x = text_pos[0] + text_surf.get_width() + 2
            cursor_top = rect.centery - text_surf.get_height() // 2
            cursor_bottom = cursor_top + text_surf.get_height()
            pygame.draw.line(self.screen, (235, 244, 255), (cursor_x, cursor_top), (cursor_x, cursor_bottom), 2)

    def _fit_input_text(self, text: str, max_width: int) -> str:
        if self._font_small.size(text)[0] <= max_width:
            return text

        ellipsis = "..."
        trimmed = text
        while trimmed and self._font_small.size(ellipsis + trimmed)[0] > max_width:
            trimmed = trimmed[1:]
        if not trimmed:
            return ellipsis
        return ellipsis + trimmed

    def _draw_stats_toggle(self, panel: pygame.Rect, key_prefix: str, y: int, active_mode: str) -> None:
        btn_w = 158
        btn_h = 36
        gap = 12
        total_w = btn_w * 2 + gap
        start_x = panel.centerx - total_w // 2

        label = self._font_tiny.render("VIEW", True, (168, 188, 220))
        self.screen.blit(label, label.get_rect(midright=(start_x - 10, y + btn_h // 2)))

        options = (("ranked", "RANKED"), ("unranked", "UNRANKED"))
        for idx, (mode_key, mode_label) in enumerate(options):
            rect = pygame.Rect(start_x + idx * (btn_w + gap), y, btn_w, btn_h)
            selected = active_mode == mode_key
            if selected:
                bg = (78, 122, 178, 235)
                border = (214, 232, 255)
                txt_color = (244, 248, 255)
            else:
                bg = (28, 40, 66, 220)
                border = (102, 132, 178)
                txt_color = (196, 210, 236)
            _draw_rounded_rect(self.screen, rect, bg, border, 2, 10)
            txt = self._font_tiny.render(mode_label, True, txt_color)
            self.screen.blit(txt, txt.get_rect(center=rect.center))
            self._button_rects[f"{key_prefix}_{mode_key}"] = rect

    def _draw_profile(self, panel: pygame.Rect) -> None:
        if not self.current_username:
            self.message = "Login first to view profile."
            self.message_color = (255, 170, 170)
            self._state = "menu"
            return

        if self._profile_cache is None:
            self._profile_cache = self.service.get_profile(self.current_username)

        profile = self._profile_cache
        if profile is None:
            msg = self._font_small.render("Profile not found.", True, (255, 180, 180))
            self.screen.blit(msg, msg.get_rect(center=(panel.centerx, panel.centery)))
        else:
            self._draw_stats_toggle(panel, "profile_mode", panel.top + 96, self._profile_view_mode)
            rows = [("ID", "Username", profile.username[:24], (130, 210, 255))]
            if self._profile_view_mode == "ranked":
                rows.extend(
                    [
                        ("RR", "Ranked RR", str(profile.rr), (255, 210, 120)),
                        ("MW", "Matches W/L", f"{profile.matches_won}/{profile.matches_played}", (140, 230, 170)),
                        ("RW", "Rounds W/L", f"{profile.rounds_won}/{profile.rounds_played}", (120, 210, 245)),
                        ("EL", "Eliminations", str(profile.eliminations), (255, 165, 120)),
                        ("KO", "Deaths", str(profile.deaths), (255, 130, 130)),
                        ("DD", "Damage Dealt", str(profile.damage_dealt), (255, 190, 110)),
                        ("DT", "Damage Taken", str(profile.damage_taken), (255, 155, 155)),
                        ("MV", "MVPs", str(profile.mvp_count), (255, 200, 140)),
                    ]
                )
            else:
                rows.extend(
                    [
                        ("UM", "Matches W/L", f"{profile.unranked_matches_won}/{profile.unranked_matches_played}", (140, 206, 255)),
                        ("UR", "Rounds W/L", f"{profile.unranked_rounds_won}/{profile.unranked_rounds_played}", (128, 214, 255)),
                        ("UE", "Eliminations", str(profile.unranked_eliminations), (255, 174, 136)),
                        ("UD", "Deaths", str(profile.unranked_deaths), (255, 148, 148)),
                        ("DD", "Damage Dealt", str(profile.unranked_damage_dealt), (255, 178, 120)),
                        ("DT", "Damage Taken", str(profile.unranked_damage_taken), (255, 166, 166)),
                        ("MV", "MVPs", str(profile.unranked_mvp_count), (255, 200, 140)),
                    ]
                )

            y = panel.top + 148
            for icon_text, label, value, accent in rows:
                self._draw_profile_stat_row(panel, y, icon_text, label, value, accent)
                y += 36

        self._draw_button(panel, "sync", "SYNC NOW", 6, color=(70, 136, 102), width=230)
        self._draw_button(panel, "back", "BACK", 7, color=(96, 96, 118), width=230)

    def _draw_profile_stat_row(
        self,
        panel: pygame.Rect,
        y: int,
        icon_text: str,
        label: str,
        value: str,
        accent: tuple[int, int, int],
    ) -> None:
        icon_center = (panel.left + 62, y + 16)
        pygame.draw.circle(self.screen, (25, 36, 58), icon_center, 15)
        pygame.draw.circle(self.screen, accent, icon_center, 15, 2)

        icon_surf = self._font_profile_icon.render(icon_text[:2], True, (242, 247, 255))
        self.screen.blit(icon_surf, icon_surf.get_rect(center=icon_center))

        label_surf = self._font_profile_label.render(label, True, (220, 232, 250))
        value_surf = self._font_profile_value.render(str(value), True, (244, 248, 255))

        label_pos = (panel.left + 92, y)
        value_rect = value_surf.get_rect(midleft=(panel.left + 330, y + 17))
        if value_rect.right > panel.right - 28:
            value_rect.right = panel.right - 28

        self.screen.blit(label_surf, label_pos)
        self.screen.blit(value_surf, value_rect)

    def _leaderboard_max_scroll_start(self) -> int:
        rows_per_page = max(1, int(self._leaderboard_rows_per_page))
        return max(0, len(self._leaderboard_cache) - rows_per_page)

    def _clamp_leaderboard_scroll(self) -> None:
        max_start = self._leaderboard_max_scroll_start()
        self._leaderboard_scroll_index = max(0, min(int(self._leaderboard_scroll_index), max_start))

    def _scroll_leaderboard(self, delta: int) -> None:
        if not self._leaderboard_cache:
            self._leaderboard_scroll_index = 0
            return
        self._leaderboard_scroll_index += int(delta)
        self._clamp_leaderboard_scroll()

    def _ensure_leaderboard_selection_visible(self) -> None:
        if not self._leaderboard_cache:
            self._leaderboard_scroll_index = 0
            return

        target = self._leaderboard_selected_username
        if not target:
            self._clamp_leaderboard_scroll()
            return

        selected_index = None
        for idx, row in enumerate(self._leaderboard_cache):
            if str(row.get("username", "")) == target:
                selected_index = idx
                break

        if selected_index is None:
            self._clamp_leaderboard_scroll()
            return

        rows_per_page = max(1, int(self._leaderboard_rows_per_page))
        window_start = int(self._leaderboard_scroll_index)
        window_end = window_start + rows_per_page - 1

        if selected_index < window_start:
            self._leaderboard_scroll_index = selected_index
        elif selected_index > window_end:
            self._leaderboard_scroll_index = selected_index - rows_per_page + 1

        self._clamp_leaderboard_scroll()

    def _draw_leaderboard_scroll_button(self, key: str, rect: pygame.Rect, label: str, enabled: bool) -> None:
        if enabled:
            bg = (54, 90, 142, 236)
            border = (198, 224, 255)
            txt_color = (245, 249, 255)
        else:
            bg = (36, 45, 68, 214)
            border = (95, 112, 146)
            txt_color = (152, 168, 194)

        _draw_rounded_rect(self.screen, rect, bg, border, 2, 10)
        txt = self._font_tiny.render(label, True, txt_color)
        self.screen.blit(txt, txt.get_rect(center=rect.center))
        self._button_rects[key] = rect

    def _draw_leaderboard(self, panel: pygame.Rect) -> None:
        mode_label = "Ranked" if self._leaderboard_view_mode == "ranked" else "Unranked"
        title = (
            f"{mode_label} online leaderboard"
            if self._leaderboard_online
            else f"Offline - {mode_label.lower()} leaderboard unavailable"
        )
        title_surf = self._font_lb_title.render(title, True, (210, 228, 255))
        self.screen.blit(title_surf, title_surf.get_rect(center=(panel.centerx, panel.top + 112)))
        self._draw_stats_toggle(panel, "leaderboard_mode", panel.top + 130, self._leaderboard_view_mode)

        list_rect = pygame.Rect(panel.left + 32, panel.top + 184, panel.width - 64, 360)
        _draw_rounded_rect(self.screen, list_rect, (20, 25, 40, 225), (90, 120, 170), 2, 12)

        max_rows = max(1, int(self._leaderboard_rows_per_page))
        self._clamp_leaderboard_scroll()

        scroll_col_w = 58
        row_left = list_rect.left + 10
        row_width = max(120, list_rect.width - 20 - scroll_col_w)
        row_right = row_left + row_width

        header_y = list_rect.top + 14
        x_pos = row_left + 8
        x_user = row_left + 66
        x_rr = row_right - 210
        x_wl = row_right - 132
        x_mvp = row_right - 58
        rating_label = "RR" if self._leaderboard_view_mode == "ranked" else "UR"

        hdr_color = (182, 204, 238)
        self.screen.blit(self._font_lb_header.render("POS", True, hdr_color), (x_pos, header_y))
        self.screen.blit(self._font_lb_header.render("USERNAME", True, hdr_color), (x_user, header_y))
        self.screen.blit(self._font_lb_header.render(rating_label, True, hdr_color), (x_rr, header_y))
        self.screen.blit(self._font_lb_header.render("W/L", True, hdr_color), (x_wl, header_y))
        self.screen.blit(self._font_lb_header.render("MVP", True, hdr_color), (x_mvp, header_y))

        pygame.draw.line(
            self.screen,
            (104, 130, 176),
            (row_left + 4, header_y + 32),
            (row_right - 4, header_y + 32),
            1,
        )

        total_rows = len(self._leaderboard_cache)
        max_start = self._leaderboard_max_scroll_start()
        start = int(self._leaderboard_scroll_index)
        can_scroll_up = start > 0
        can_scroll_down = start < max_start
        scroll_x = row_right + 8
        up_rect = pygame.Rect(scroll_x, header_y + 40, scroll_col_w - 8, 42)
        down_rect = pygame.Rect(scroll_x, list_rect.bottom - 58, scroll_col_w - 8, 42)
        self._draw_leaderboard_scroll_button("leaderboard_scroll_up", up_rect, "UP", can_scroll_up)
        self._draw_leaderboard_scroll_button("leaderboard_scroll_down", down_rect, "DOWN", can_scroll_down)

        if total_rows > 0:
            visible_start = start + 1
            visible_end = min(total_rows, start + max_rows)
            range_label = f"{visible_start}-{visible_end}"
        else:
            range_label = "0-0"
        range_txt = self._font_tiny.render(f"{range_label} / {total_rows}", True, (172, 194, 228))
        range_center_y = up_rect.bottom + ((down_rect.top - up_rect.bottom) // 2)
        self.screen.blit(range_txt, range_txt.get_rect(center=(up_rect.centerx, range_center_y)))

        if not self._leaderboard_online:
            offline = self._font_lb_meta.render("Connect to internet and set GRID_SURVIVAL_API_URL", True, (255, 190, 170))
            self.screen.blit(offline, offline.get_rect(center=list_rect.center))
        else:
            if self._leaderboard_cache and not self._leaderboard_selected_username:
                self._leaderboard_selected_username = str(self._leaderboard_cache[0].get("username", "")) or None

            self._ensure_leaderboard_selection_visible()
            start = int(self._leaderboard_scroll_index)
            visible_rows = self._leaderboard_cache[start:start + max_rows]

            y = header_y + 42
            row_h = 34
            for absolute_index, row in enumerate(visible_rows, start=start):
                username = str(row.get("username", ""))
                is_me = bool(self.current_username and username == self.current_username)
                is_selected = bool(self._leaderboard_selected_username and username == self._leaderboard_selected_username)
                row_rect = pygame.Rect(row_left, y - 2, row_width, row_h)
                if is_selected and is_me:
                    row_bg = (64, 74, 36, 220)
                    row_border = (255, 220, 120)
                    text_color = (255, 236, 164)
                elif is_selected:
                    row_bg = (44, 62, 98, 220)
                    row_border = (162, 202, 255)
                    text_color = (244, 248, 255)
                elif is_me:
                    row_bg = (56, 70, 36, 220)
                    row_border = (240, 204, 116)
                    text_color = (255, 236, 164)
                else:
                    row_bg = (28, 36, 62, 210) if (absolute_index % 2 == 0) else (24, 31, 54, 210)
                    row_border = (88, 112, 158)
                    text_color = (232, 238, 250)
                _draw_rounded_rect(self.screen, row_rect, row_bg, row_border, 1, 8)
                self._leaderboard_row_hitboxes.append((row_rect.copy(), username))

                pos_text = str(int(row.get("position", absolute_index + 1)))
                name_text = username[:18]
                rr_text = str(int(row.get("rating", row.get("rr", 0))))
                wl_text = f"{int(row.get('matches_won', 0))}/{int(row.get('matches_played', 0))}"
                mvp_text = str(int(row.get("mvp_count", 0)))

                self.screen.blit(self._font_lb_row.render(pos_text, True, text_color), (x_pos, y + 3))
                self.screen.blit(self._font_lb_row.render(name_text, True, text_color), (x_user, y + 3))
                self.screen.blit(self._font_lb_row.render(rr_text, True, text_color), (x_rr, y + 3))
                self.screen.blit(self._font_lb_row.render(wl_text, True, text_color), (x_wl, y + 3))
                self.screen.blit(self._font_lb_row.render(mvp_text, True, text_color), (x_mvp, y + 3))
                y += row_h + 6

            selected_row = self._get_selected_leaderboard_row()
            self._draw_leaderboard_player_box(panel, selected_row)

            hint = self._font_tiny.render("", True, (170, 190, 220))
            self.screen.blit(hint, hint.get_rect(midleft=(list_rect.left + 6, list_rect.bottom + 2)))

            if self.current_username:
                position = self._find_position(self.current_username)
                if position is not None:
                    pos_line = self._font_lb_meta.render(
                        f"Your position: #{position}",
                        True,
                        (255, 225, 130),
                    )
                    self.screen.blit(pos_line, pos_line.get_rect(center=(panel.centerx, list_rect.top)))

        self._draw_button(panel, "refresh", "REFRESH", 6, color=(72, 120, 175), width=220)
        self._draw_button(panel, "back", "BACK", 7, color=(96, 96, 118), width=220)

    def _find_position(self, username: str) -> int | None:
        for row in self._leaderboard_cache:
            if row.get("username") == username:
                return int(row.get("position", 0))
        return None

    def _get_selected_leaderboard_row(self) -> dict | None:
        if not self._leaderboard_cache:
            return None

        target = self._leaderboard_selected_username
        if target:
            for row in self._leaderboard_cache:
                if str(row.get("username", "")) == target:
                    return row

        return self._leaderboard_cache[0]

    def _draw_leaderboard_player_box(self, panel: pygame.Rect, selected_row: dict | None) -> None:
        box_left = panel.right + 16
        box_width = self.width - box_left - 24
        if box_width < 260:
            return

        box_rect = pygame.Rect(box_left, panel.top + 94, box_width, panel.height - 130)
        _draw_rounded_rect(self.screen, box_rect, (18, 26, 46, 230), (116, 150, 204), 3, 14)

        heading = self._font_lb_detail_title.render("PLAYER DETAILS", True, (232, 242, 255))
        self.screen.blit(heading, heading.get_rect(center=(box_rect.centerx, box_rect.top + 34)))

        if selected_row is None:
            empty = self._font_lb_detail_label.render("No player selected yet.", True, (200, 214, 238))
            tip = self._font_tiny.render("Select a row in leaderboard to view full stats.", True, (170, 190, 220))
            self.screen.blit(empty, empty.get_rect(center=(box_rect.centerx, box_rect.centery - 4)))
            self.screen.blit(tip, tip.get_rect(center=(box_rect.centerx, box_rect.centery + 24)))
            return

        mode_short = "RR" if self._leaderboard_view_mode == "ranked" else "UR"
        username = str(selected_row.get("username", ""))[:22]
        position = int(selected_row.get("position", 0))
        rating = int(selected_row.get("rating", selected_row.get("rr", 0)))

        name_surf = self._font_lb_detail_title.render(username, True, (255, 238, 170))
        meta_surf = self._font_lb_detail_label.render(
            f"#{position}   {mode_short}: {rating}",
            True,
            (212, 226, 248),
        )
        self.screen.blit(name_surf, name_surf.get_rect(midtop=(box_rect.centerx, box_rect.top + 58)))
        self.screen.blit(meta_surf, meta_surf.get_rect(midtop=(box_rect.centerx, box_rect.top + 94)))

        stats = [
            ("MW", "Matches W/L", f"{int(selected_row.get('matches_won', 0))}/{int(selected_row.get('matches_played', 0))}", (122, 206, 150)),
            ("RW", "Rounds W/L", f"{int(selected_row.get('rounds_won', 0))}/{int(selected_row.get('rounds_played', 0))}", (118, 192, 242)),
            ("KD", "K / D", f"{int(selected_row.get('eliminations', 0))}/{int(selected_row.get('deaths', 0))}", (252, 178, 120)),
            (
                "DG",
                "Damage D/T",
                f"{int(selected_row.get('damage_dealt', 0))}/{int(selected_row.get('damage_taken', 0))}",
                (255, 148, 148),
            ),
            ("MV", "MVP", str(int(selected_row.get('mvp_count', 0))), (255, 210, 120)),
        ]

        row_y = box_rect.top + 136
        row_h = 60
        for icon_text, label, value, accent in stats:
            row_rect = pygame.Rect(box_rect.left + 12, row_y, box_rect.width - 24, row_h)
            _draw_rounded_rect(self.screen, row_rect, (23, 34, 58, 226), (96, 122, 170), 1, 10)

            icon_rect = pygame.Rect(row_rect.left + 10, row_rect.top + 11, 40, 38)
            _draw_rounded_rect(self.screen, icon_rect, (36, 52, 84, 236), accent, 2, 8)
            icon_surf = self._font_lb_detail_icon.render(icon_text, True, (245, 248, 255))
            self.screen.blit(icon_surf, icon_surf.get_rect(center=icon_rect.center))

            label_surf = self._font_lb_detail_label.render(label, True, (214, 228, 248))
            value_surf = self._font_lb_detail_value.render(value, True, (248, 252, 255))
            self.screen.blit(label_surf, label_surf.get_rect(midleft=(row_rect.left + 62, row_rect.centery - 12)))
            self.screen.blit(value_surf, value_surf.get_rect(midleft=(row_rect.left + 62, row_rect.centery + 12)))

            row_y += row_h + 8

    def _handle_menu_event(self, event: pygame.event.Event) -> dict[str, str | None] | None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self._cancel_switch_account():
                return None
            return {"action": "back", "player_name": None, "account_username": None}

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None

        pos = event.pos
        if self._button_rects.get("login") and self._button_rects["login"].collidepoint(pos):
            self._state = "login"
            self.message = ""
            self.message_color = (220, 220, 235)
            self._password_input = ""
            self._focus = "username"
            return None

        if self._button_rects.get("register") and self._button_rects["register"].collidepoint(pos):
            self._state = "register"
            self.message = ""
            self.message_color = (220, 220, 235)
            self._password_input = ""
            self._focus = "username"
            return None

        if self._button_rects.get("switch") and self._button_rects["switch"].collidepoint(pos):
            if self.current_username:
                self._switch_from_username = self.current_username
                self._switching_account = True
            self.current_username = None
            self._profile_cache = None
            self._username_input = self._suggested_username
            self._password_input = ""
            self.message = "Select another account, or press BACK to cancel."
            self.message_color = (190, 220, 255)
            return None

        if self._button_rects.get("profile") and self._button_rects["profile"].collidepoint(pos):
            self._profile_cache = self.service.get_profile(self.current_username or "")
            if self._profile_cache is None:
                self.message = "Profile unavailable."
                self.message_color = (255, 180, 180)
            self._state = "profile"
            return None

        if self._button_rects.get("leaderboard") and self._button_rects["leaderboard"].collidepoint(pos):
            self._refresh_leaderboard()
            self._state = "leaderboard"
            return None

        if self._button_rects.get("continue_account") and self._button_rects["continue_account"].collidepoint(pos):
            if self.current_username:
                return {
                    "action": "continue",
                    "player_name": self.current_username,
                    "account_username": self.current_username,
                }

        if self._button_rects.get("back") and self._button_rects["back"].collidepoint(pos):
            if self._cancel_switch_account():
                return None
            return {"action": "back", "player_name": None, "account_username": None}

        return None

    def _handle_auth_event(self, event: pygame.event.Event) -> dict[str, str | None] | None:
        if self._auth_popup_visible:
            self._handle_auth_popup_event(event)
            return None

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._state = "menu"
                self.message = ""
                self._clear_auth_popup()
                return None
            if event.key == pygame.K_TAB:
                self._focus = "password" if self._focus == "username" else "username"
                return None
            if event.key == pygame.K_BACKSPACE:
                if self._focus == "username":
                    self._username_input = self._username_input[:-1]
                else:
                    self._password_input = self._password_input[:-1]
                return None
            if event.key == pygame.K_RETURN:
                self._submit_auth()
                return None
            if event.unicode and event.unicode.isprintable():
                if self._focus == "username" and len(self._username_input) < 24:
                    self._username_input += event.unicode
                elif self._focus == "password" and len(self._password_input) < 48:
                    self._password_input += event.unicode
                return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self._auth_username_rect.collidepoint(pos):
                self._focus = "username"
                return None
            if self._auth_password_rect.collidepoint(pos):
                self._focus = "password"
                return None
            if self._button_rects.get("submit") and self._button_rects["submit"].collidepoint(pos):
                self._submit_auth()
                return None
            if self._button_rects.get("cancel") and self._button_rects["cancel"].collidepoint(pos):
                self._state = "menu"
                self.message = ""
                self._clear_auth_popup()
                return None

        return None

    def _submit_auth(self) -> None:
        username = self._username_input.strip()
        password = self._password_input

        if self._state == "register":
            ok, msg = self.service.register_account(username, password)
            if ok:
                self.current_username = username
                self._profile_cache = self.service.get_profile(username)
                self._switching_account = False
                self._switch_from_username = None
                self._state = "menu"
                self.message = "Account created and signed in."
                self.message_color = (170, 235, 180)
                self._password_input = ""
            else:
                self.message = msg
                self.message_color = (255, 175, 175)
            return

        ok, msg = self.service.authenticate(username, password)
        if ok:
            self.current_username = username
            self._profile_cache = self.service.get_profile(username)
            self._switching_account = False
            self._switch_from_username = None
            self._state = "menu"
            self.message = "Login successful."
            self.message_color = (170, 235, 180)
            self._password_input = ""
            self._clear_auth_popup()
        else:
            self.message = msg
            self.message_color = (255, 175, 175)
            self._show_login_guidance_popup(msg)

    def _handle_profile_event(self, event: pygame.event.Event) -> dict[str, str | None] | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._state = "menu"
                return None
            if event.key == pygame.K_TAB:
                self._profile_view_mode = "unranked" if self._profile_view_mode == "ranked" else "ranked"
                return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self._button_rects.get("profile_mode_ranked") and self._button_rects["profile_mode_ranked"].collidepoint(pos):
                self._profile_view_mode = "ranked"
                return None
            if self._button_rects.get("profile_mode_unranked") and self._button_rects["profile_mode_unranked"].collidepoint(pos):
                self._profile_view_mode = "unranked"
                return None
            if self._button_rects.get("sync") and self._button_rects["sync"].collidepoint(pos):
                if self.current_username:
                    set_menu_sync_indicator_running()
                    synced = False
                    try:
                        synced = bool(self.service.sync_pending(self.current_username))
                    except Exception:
                        synced = False
                    set_menu_sync_indicator_result(synced)
                    self._profile_cache = self.service.get_profile(self.current_username)
                    self.message = "Synced with VPS." if synced else "Sync skipped (offline or API unavailable)."
                    self.message_color = (180, 210, 255) if synced else (255, 210, 165)
                return None
            if self._button_rects.get("back") and self._button_rects["back"].collidepoint(pos):
                self._state = "menu"
                return None

        return None

    def _handle_leaderboard_event(self, event: pygame.event.Event) -> dict[str, str | None] | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self._state = "menu"
                return None
            if event.key == pygame.K_TAB:
                self._leaderboard_view_mode = "unranked" if self._leaderboard_view_mode == "ranked" else "ranked"
                self._refresh_leaderboard()
                return None
            if event.key == pygame.K_UP:
                self._scroll_leaderboard(-1)
                return None
            if event.key == pygame.K_DOWN:
                self._scroll_leaderboard(1)
                return None
            if event.key == pygame.K_PAGEUP:
                self._scroll_leaderboard(-self._leaderboard_rows_per_page)
                return None
            if event.key == pygame.K_PAGEDOWN:
                self._scroll_leaderboard(self._leaderboard_rows_per_page)
                return None

        if event.type == pygame.MOUSEWHEEL:
            if event.y > 0:
                self._scroll_leaderboard(-1)
            elif event.y < 0:
                self._scroll_leaderboard(1)
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (4, 5):
            if event.button == 4:
                self._scroll_leaderboard(-1)
            else:
                self._scroll_leaderboard(1)
            return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pos = event.pos
            if self._button_rects.get("leaderboard_scroll_up") and self._button_rects["leaderboard_scroll_up"].collidepoint(pos):
                self._scroll_leaderboard(-1)
                return None
            if self._button_rects.get("leaderboard_scroll_down") and self._button_rects["leaderboard_scroll_down"].collidepoint(pos):
                self._scroll_leaderboard(1)
                return None

            for row_rect, username in self._leaderboard_row_hitboxes:
                if row_rect.collidepoint(pos):
                    if username:
                        self._leaderboard_selected_username = username
                    return None

            if self._button_rects.get("leaderboard_mode_ranked") and self._button_rects["leaderboard_mode_ranked"].collidepoint(pos):
                if self._leaderboard_view_mode != "ranked":
                    self._leaderboard_view_mode = "ranked"
                    self._refresh_leaderboard()
                return None
            if self._button_rects.get("leaderboard_mode_unranked") and self._button_rects["leaderboard_mode_unranked"].collidepoint(pos):
                if self._leaderboard_view_mode != "unranked":
                    self._leaderboard_view_mode = "unranked"
                    self._refresh_leaderboard()
                return None
            if self._button_rects.get("refresh") and self._button_rects["refresh"].collidepoint(pos):
                self._refresh_leaderboard()
                return None
            if self._button_rects.get("back") and self._button_rects["back"].collidepoint(pos):
                self._state = "menu"
                return None

        return None

    def _refresh_leaderboard(self) -> None:
        online = self.service.is_remote_online()
        self._leaderboard_online = bool(online)
        self._remote_online = bool(online)
        self._remote_check_timer = 0.0
        mode_label = "Ranked" if self._leaderboard_view_mode == "ranked" else "Unranked"
        if online:
            entries = self.service.fetch_remote_leaderboard(
                limit=50,
                mode=self._leaderboard_view_mode,
            ) or []
            self._leaderboard_cache = entries
            if self.current_username and any(str(row.get("username", "")) == self.current_username for row in entries):
                self._leaderboard_selected_username = self.current_username
            elif self._leaderboard_selected_username and any(
                str(row.get("username", "")) == self._leaderboard_selected_username for row in entries
            ):
                pass
            elif entries:
                self._leaderboard_selected_username = str(entries[0].get("username", "")) or None
            else:
                self._leaderboard_selected_username = None
            self._clamp_leaderboard_scroll()
            self._ensure_leaderboard_selection_visible()
            self.message = f"{mode_label} leaderboard refreshed."
            self.message_color = (180, 215, 255)
        else:
            self._leaderboard_cache = []
            self._leaderboard_selected_username = None
            self._leaderboard_scroll_index = 0
            self.message = f"Online connection required for {mode_label.lower()} leaderboard."
            self.message_color = (255, 200, 170)

    def _open_tutorial_from_title(self) -> None:
        self._title_shell._play_multipage_tutorial()

    def _open_controls_editor_from_title(self) -> None:
        self._title_shell._customize_controls()

    def _fade(self, mode: str) -> None:
        overlay = pygame.Surface(WINDOW_SIZE)
        alpha = 255 if mode == "in" else 0
        step = SCENE_FADE_SPEED / TARGET_FPS

        while True:
            if mode == "in":
                alpha -= step
                if alpha <= 0:
                    alpha = 0
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
