from __future__ import annotations

import math
import sys
from dataclasses import dataclass

import pygame

from backend.online_service import OnlineService
from lan_prompts import draw_lan_backdrop, prompt_ip_entry
from settings import (
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    FONT_PATH_SMALL,
    SOUND_MATCH_FOUND,
    WINDOW_SIZE,
    SOUND_POWER_READY,
)
from .common import SceneAudioOverlay, _draw_rounded_rect, _load_font
from audio import get_audio


@dataclass
class InternetLobbySetup:
    player_name: str
    character_name: str
    level_id: int
    target_score: int
    player_count: int
    rating: int


class InternetPartyLobbyScreen:
    """Control-plane lobby scene for internet party/queue flow."""

    def __init__(
        self,
        screen: pygame.Surface,
        clock: pygame.time.Clock,
        online_service: OnlineService,
        setup: InternetLobbySetup,
    ) -> None:
        self.screen = screen
        self.clock = clock
        self.online_service = online_service
        self.setup = setup

        self.width, self.height = WINDOW_SIZE
        self._audio_overlay = SceneAudioOverlay()
        self.quit_requested = False

        self._font_title = _load_font(FONT_PATH_HEADING, 32, bold=True)
        self._font_body = _load_font(FONT_PATH_BODY, 22)
        self._font_small = _load_font(FONT_PATH_SMALL, 18)

        self._selected = 0
        self._anim_time = 0.0

        self._lobby: dict | None = None
        self._lobby_code = ""
        self._in_queue = False
        self._ready = False
        self._queue_started_at = 0.0
        self._status_text = "Create or join a lobby to start."
        self._status_ttl = 0.0

    def _set_status(self, text: str, ttl: float = 2.2) -> None:
        self._status_text = str(text)
        self._status_ttl = max(0.0, float(ttl))

    def _lobby_members(self) -> list[dict]:
        if not isinstance(self._lobby, dict):
            return []
        members = self._lobby.get("members")
        if isinstance(members, list):
            return [m for m in members if isinstance(m, dict)]
        return []

    def _refresh_updates(self) -> dict | None:
        res = self.online_service.poll_or_ws_updates(player_name=self.setup.player_name)
        if not res.get("ok"):
            return None

        lobby = res.get("lobby")
        if isinstance(lobby, dict):
            self._lobby = lobby
            self._lobby_code = str(lobby.get("code", self._lobby_code))
            self._in_queue = bool(lobby.get("queued", False))

        events = res.get("events") or []
        for event in events:
            if not isinstance(event, dict):
                continue
            etype = str(event.get("type", ""))
            if etype == "match_found":
                match = event.get("match")
                if isinstance(match, dict):
                    if bool(match.get("pending_config")):
                        return match
                    return match
            if etype == "match_configured":
                match = event.get("match")
                if isinstance(match, dict):
                    return match
            if etype == "queue_joined":
                self._in_queue = True
                if self._queue_started_at <= 0.0:
                    self._queue_started_at = pygame.time.get_ticks() / 1000.0
            if etype == "queue_left":
                self._in_queue = False
        return None

    def _action_create_lobby(self) -> None:
        res = self.online_service.create_lobby(
            player_name=self.setup.player_name,
            mode="ranked",
            target_score=int(self.setup.target_score),
            map_pool=[int(self.setup.level_id)],
            region="global",
            max_players=int(self.setup.player_count),
            rating=int(self.setup.rating),
        )
        if not res.get("ok"):
            self._set_status(f"Create failed: {res.get('error', 'unknown')}")
            return
        lobby = res.get("lobby")
        if not isinstance(lobby, dict):
            self._set_status("Create failed: invalid lobby payload")
            return
        self._lobby = lobby
        self._lobby_code = str(lobby.get("code", "")).upper()
        self._in_queue = False
        self._ready = False
        self._set_status(f"Lobby {self._lobby_code} created")

    def _prompt_lobby_code(self) -> str | None:
        """Show a small modal to enter a lobby code (letters/digits/hyphen allowed)."""
        width, height = WINDOW_SIZE
        card_w = min(max(640, 640), width - 120)
        card_h = max(230, 230)
        font_title = self._font_title
        font_body = self._font_body
        font_small = self._font_small
        audio_overlay = SceneAudioOverlay()
        input_str = ""
        btn_w, btn_h = 180, 52
        btn_gap = 18
        card_rect = pygame.Rect(0, 0, card_w, card_h)
        card_rect.center = (width // 2, height // 2 + 10)
        btn_confirm = pygame.Rect(0, 0, btn_w, btn_h)
        btn_back = pygame.Rect(0, 0, btn_w, btn_h)
        btn_confirm.center = (width // 2 + btn_w // 2 + btn_gap // 2, card_rect.bottom + 46)
        btn_back.center = (width // 2 - btn_w // 2 - btn_gap // 2, card_rect.bottom + 46)

        def draw(show_cursor: bool = True):
            draw_lan_backdrop(self.screen, self._anim_time)
            _draw_rounded_rect(self.screen, card_rect, (24, 30, 50), (110, 130, 180), 3, 18)
            title = font_title.render("Enter Lobby Code", True, (255, 255, 255))
            self.screen.blit(title, title.get_rect(center=(card_rect.centerx, card_rect.top + 36)))

            help = font_small.render("Enter the party code (letters and digits). Example: ABCD-1234", True, (200, 205, 220))
            self.screen.blit(help, help.get_rect(center=(card_rect.centerx, card_rect.top + 80)))

            input_box = pygame.Rect(card_rect.left + 42, card_rect.centery - 6, card_rect.width - 84, 62)
            _draw_rounded_rect(self.screen, input_box, (12, 20, 38), (100, 120, 160), 2, 14)
            display = input_str + ("_" if show_cursor else "")
            txt = font_body.render(display, True, (255, 220, 90))
            self.screen.blit(txt, txt.get_rect(midleft=(input_box.left + 12, input_box.centery + 1)))

            tip = font_small.render("Letters, digits and '-' allowed", True, (165, 175, 205))
            self.screen.blit(tip, tip.get_rect(center=(card_rect.centerx, input_box.bottom + 22)))

            mouse_pos = pygame.mouse.get_pos()
            for rect, label in ((btn_back, "Back"), (btn_confirm, "Join")):
                hovered = rect.collidepoint(mouse_pos)
                bg = (40, 54, 88) if not hovered else (54, 72, 110)
                border = (108, 128, 170) if not hovered else (170, 200, 255)
                _draw_rounded_rect(self.screen, rect, bg + (220,), border + (255,), 2, 12)
                lab = font_small.render(label.upper(), True, border)
                self.screen.blit(lab, lab.get_rect(center=rect.center))

            footer = font_small.render("ENTER to join  *  ESC to cancel", True, (175, 185, 205))
            self.screen.blit(footer, footer.get_rect(center=(width // 2, height - 44)))
            audio_overlay.draw(self.screen)
            pygame.display.flip()

        cursor_timer = 0.0
        while True:
            dt = self.clock.tick(60) / 1000.0
            cursor_timer += dt
            show_cursor = (int(cursor_timer * 2) % 2) == 0
            draw(show_cursor)
            for event in pygame.event.get():
                if audio_overlay.handle_event(event):
                    continue
                if event.type == pygame.QUIT:
                    self.quit_requested = True
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN and input_str:
                        return input_str
                    elif event.key == pygame.K_BACKSPACE:
                        input_str = input_str[:-1]
                    elif event.key == pygame.K_ESCAPE:
                        return None
                    elif event.unicode and len(input_str) < 32:
                        ch = event.unicode.upper()
                        if ch.isalnum() or ch == '-':
                            input_str += ch
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if btn_confirm.collidepoint(event.pos) and input_str:
                        return input_str
                    if btn_back.collidepoint(event.pos):
                        return None

    def _action_join_lobby(self) -> None:
        code = self._prompt_lobby_code()
        if not code:
            return
        # normalize to alphanumeric code (remove punctuation except digits/letters)
        clean = "".join(ch for ch in str(code).strip().upper() if ch.isalnum())
        res = self.online_service.join_lobby(
            player_name=self.setup.player_name,
            lobby_code=clean,
            rating=int(self.setup.rating),
        )
        if not res.get("ok"):
            self._set_status(f"Join failed: {res.get('error', 'unknown')}")
            return
        lobby = res.get("lobby")
        if not isinstance(lobby, dict):
            self._set_status("Join failed: invalid lobby payload")
            return
        self._lobby = lobby
        self._lobby_code = str(lobby.get("code", clean)).upper()
        self._in_queue = bool(lobby.get("queued", False))
        self._ready = False
        self._set_status(f"Joined lobby {self._lobby_code}")

    def _action_toggle_ready(self) -> None:
        if not self._lobby_code:
            self._set_status("Create or join a lobby first")
            return
        self._ready = not self._ready
        res = self.online_service.set_ready(
            player_name=self.setup.player_name,
            lobby_code=self._lobby_code,
            ready=self._ready,
        )
        if not res.get("ok"):
            self._ready = not self._ready
            self._set_status(f"Ready failed: {res.get('error', 'unknown')}")
            return
        self._lobby = res.get("lobby") if isinstance(res.get("lobby"), dict) else self._lobby
        self._set_status("Ready" if self._ready else "Not ready")

    def _action_toggle_queue(self) -> None:
        if not self._lobby_code:
            self._set_status("Create or join a lobby first")
            return
        if self._in_queue:
            res = self.online_service.dequeue(
                player_name=self.setup.player_name,
                lobby_code=self._lobby_code,
            )
            if not res.get("ok"):
                self._set_status(f"Dequeue failed: {res.get('error', 'unknown')}")
                return
            self._in_queue = False
            self._set_status("Queue canceled")
            return

        res = self.online_service.queue(
            player_name=self.setup.player_name,
            lobby_code=self._lobby_code,
            region="global",
            rating=int(self.setup.rating),
        )
        if not res.get("ok"):
            self._set_status(f"Queue failed: {res.get('error', 'unknown')}")
            return
        self._in_queue = True
        self._queue_started_at = pygame.time.get_ticks() / 1000.0
        self._set_status("Queued for match")

    def _draw(self) -> None:
        draw_lan_backdrop(self.screen, self._anim_time)

        panel = pygame.Rect(0, 0, min(1100, self.width - 90), min(620, self.height - 90))
        panel.center = (self.width // 2, self.height // 2)
        _draw_rounded_rect(self.screen, panel, (16, 22, 38, 236), (128, 154, 210), 3, 18)

        title = self._font_title.render("INTERNET PARTY LOBBY", True, (245, 249, 255))
        self.screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 40)))

        meta_line = (
            f"{self.setup.player_name} ({self.setup.character_name}) * "
            f"Map {self.setup.level_id} * Target {self.setup.target_score} * Slots {self.setup.player_count}"
        )
        meta = self._font_small.render(meta_line, True, (180, 198, 230))
        self.screen.blit(meta, meta.get_rect(center=(panel.centerx, panel.top + 74)))

        lobby_code = self._lobby_code or "-"
        queue_secs = 0
        if self._in_queue and self._queue_started_at > 0.0:
            queue_secs = max(0, int((pygame.time.get_ticks() / 1000.0) - self._queue_started_at))

        status_top = panel.top + 108
        status_line = self._font_body.render(
            f"Lobby: {lobby_code}   Ready: {'YES' if self._ready else 'NO'}   Queue: {'ON' if self._in_queue else 'OFF'} ({queue_secs}s)",
            True,
            (220, 230, 248),
        )
        self.screen.blit(status_line, status_line.get_rect(center=(panel.centerx, status_top)))

        members_title = self._font_body.render("Party Roster", True, (240, 244, 255))
        self.screen.blit(members_title, members_title.get_rect(midleft=(panel.left + 34, panel.top + 150)))

        members_rect = pygame.Rect(panel.left + 30, panel.top + 178, panel.width - 60, 230)
        _draw_rounded_rect(self.screen, members_rect, (26, 34, 58, 220), (102, 128, 178), 2, 12)

        members = self._lobby_members()
        if not members:
            empty = self._font_small.render("No party data yet. Create or join a lobby.", True, (168, 184, 214))
            self.screen.blit(empty, empty.get_rect(midleft=(members_rect.left + 18, members_rect.top + 28)))
        else:
            y = members_rect.top + 20
            for idx, member in enumerate(members[:8]):
                name = str(member.get("name", f"Player {idx + 1}"))
                ready = bool(member.get("ready", False))
                rating = int(member.get("rating", 1000))
                character = str(member.get("character", "")).strip()
                dot = (120, 232, 170) if ready else (236, 160, 136)
                pygame.draw.circle(self.screen, dot, (members_rect.left + 16, y + 11), 6)
                character_text = f"  {character}" if character else ""
                line = self._font_small.render(f"{name}{character_text}  RR:{rating}  {'READY' if ready else 'WAITING'}", True, (228, 236, 252))
                self.screen.blit(line, (members_rect.left + 28, y))
                y += 26

        actions = [
            ("CREATE LOBBY", "C"),
            ("JOIN BY CODE", "J"),
            ("TOGGLE READY", "R"),
            ("QUEUE / CANCEL", "Q"),
            ("BACK", "ESC"),
        ]
        cards_top = members_rect.bottom + 20
        card_w = (panel.width - 72 - 16 * 4) // 5
        mouse_pos = pygame.mouse.get_pos()
        for idx, (label, key) in enumerate(actions):
            rect = pygame.Rect(panel.left + 30 + idx * (card_w + 16), cards_top, card_w, 70)
            active = rect.collidepoint(mouse_pos) or idx == self._selected
            border = (170, 132, 255) if active else (108, 128, 170)
            bg = (40, 54, 88, 235) if active else (30, 42, 70, 225)
            _draw_rounded_rect(self.screen, rect, bg, border, 2, 12)
            txt = self._font_small.render(label, True, (246, 249, 255))
            ktxt = self._font_small.render(f"[{key}]", True, border)
            self.screen.blit(txt, txt.get_rect(center=(rect.centerx, rect.centery - 10)))
            self.screen.blit(ktxt, ktxt.get_rect(center=(rect.centerx, rect.centery + 14)))

        if self._status_text:
            color = (192, 220, 255) if self._status_ttl > 0 else (166, 182, 210)
            status = self._font_small.render(self._status_text, True, color)
            self.screen.blit(status, status.get_rect(center=(panel.centerx, panel.bottom - 20)))

        self._audio_overlay.draw(self.screen)

    def _show_match_found(self, match: dict) -> bool:
        """Show a short 'MATCH FOUND' overlay with countdown. Returns True if accepted."""
        countdown = 3.0
        # play SFX once on match found
        try:
            get_audio().play_sfx(SOUND_MATCH_FOUND, volume=0.95, max_instances=1)
        except Exception:
            pass
        start = pygame.time.get_ticks() / 1000.0
        while True:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if self._audio_overlay.handle_event(event):
                    continue
                if event.type == pygame.QUIT:
                    self.quit_requested = True
                    return False
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        # decline the match and leave queue
                        if self._lobby_code:
                            try:
                                self.online_service.dequeue(player_name=self.setup.player_name, lobby_code=self._lobby_code)
                            except Exception:
                                pass
                        self._set_status("Match declined", ttl=1.6)
                        return False

            elapsed = (pygame.time.get_ticks() / 1000.0) - start
            remaining = max(0, int(math.ceil(countdown - elapsed)))

            # draw base lobby behind overlay so players see context
            self._draw()

            # overlay
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            overlay.fill((6, 10, 18, 160))
            self.screen.blit(overlay, (0, 0))

            panel_w = min(640, self.width - 120)
            panel_h = 260
            panel = pygame.Rect(0, 0, panel_w, panel_h)
            panel.center = (self.width // 2, self.height // 2)
            _draw_rounded_rect(self.screen, panel, (18, 22, 36, 240), (190, 110, 255), 3, 12)

            title_font = _load_font(FONT_PATH_HEADING, 36, bold=True)
            title_surf = title_font.render("MATCH FOUND", True, (255, 255, 255))
            self.screen.blit(title_surf, title_surf.get_rect(center=(panel.centerx, panel.top + 42)))

            # show players (from match payload) and map
            players = match.get("players") or []
            map_id = match.get("map_id") or match.get("map") or self.setup.level_id
            y = panel.top + 92
            info_font = _load_font(FONT_PATH_BODY, 20)
            try:
                for idx, p in enumerate(players[:4]):
                    name = str(p.get("name", f"Player {idx + 1}")) if isinstance(p, dict) else str(p)
                    line = info_font.render(name, True, (230, 238, 255))
                    self.screen.blit(line, (panel.left + 36, y))
                    y += 26
            except Exception:
                pass

            map_s = info_font.render(f"Map: {map_id}", True, (200, 216, 238))
            self.screen.blit(map_s, (panel.right - 180, panel.top + 92))

            # countdown number
            count_font = _load_font(FONT_PATH_HEADING, 72, bold=True)
            count_s = count_font.render(str(remaining), True, (255, 220, 110))
            self.screen.blit(count_s, count_s.get_rect(center=(panel.centerx, panel.bottom - 58)))

            hint = self._font_small.render("Press ESC to decline", True, (190, 200, 220))
            self.screen.blit(hint, hint.get_rect(center=(panel.centerx, panel.bottom - 22)))

            self._audio_overlay.draw(self.screen)
            pygame.display.flip()

            if elapsed >= countdown:
                return True

    def _run_action(self, idx: int) -> None:
        if idx == 0:
            self._action_create_lobby()
        elif idx == 1:
            self._action_join_lobby()
        elif idx == 2:
            self._action_toggle_ready()
        elif idx == 3:
            self._action_toggle_queue()

    def run(self) -> dict | None:
        poll_timer = 0.0
        while True:
            dt = self.clock.tick(60) / 1000.0
            self._anim_time += dt
            poll_timer += dt
            if self._status_ttl > 0.0:
                self._status_ttl = max(0.0, self._status_ttl - dt)

            for event in pygame.event.get():
                if self._audio_overlay.handle_event(event):
                    continue
                if event.type == pygame.QUIT:
                    self.quit_requested = True
                    return None
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                        if self._in_queue and self._lobby_code:
                            self.online_service.dequeue(player_name=self.setup.player_name, lobby_code=self._lobby_code)
                        return None
                    if event.key in (pygame.K_LEFT, pygame.K_a):
                        self._selected = (self._selected - 1) % 5
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        self._selected = (self._selected + 1) % 5
                    elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if self._selected == 4:
                            if self._in_queue and self._lobby_code:
                                self.online_service.dequeue(player_name=self.setup.player_name, lobby_code=self._lobby_code)
                            return None
                        self._run_action(self._selected)
                    elif event.key == pygame.K_c:
                        self._run_action(0)
                    elif event.key == pygame.K_j:
                        self._run_action(1)
                    elif event.key == pygame.K_r:
                        self._run_action(2)
                    elif event.key == pygame.K_q:
                        self._run_action(3)
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    panel = pygame.Rect(0, 0, min(1100, self.width - 90), min(620, self.height - 90))
                    panel.center = (self.width // 2, self.height // 2)
                    card_w = (panel.width - 72 - 16 * 4) // 5
                    cards_top = panel.top + 178 + 230 + 20
                    for idx in range(5):
                        rect = pygame.Rect(panel.left + 30 + idx * (card_w + 16), cards_top, card_w, 70)
                        if rect.collidepoint(event.pos):
                            self._selected = idx
                            if idx == 4:
                                if self._in_queue and self._lobby_code:
                                    self.online_service.dequeue(player_name=self.setup.player_name, lobby_code=self._lobby_code)
                                return None
                            self._run_action(idx)
                            break

            if poll_timer >= 0.9:
                poll_timer = 0.0
                match = self._refresh_updates()
                if isinstance(match, dict):
                    is_owner = bool(self._lobby) and str(self._lobby.get("owner", "")).strip() == str(self.setup.player_name).strip()
                    if bool(match.get("pending_config")):
                        if is_owner:
                            return match
                        self._set_status("Match found. Waiting for the party leader to finalize setup...", ttl=2.0)
                        continue
                    accepted = self._show_match_found(match)
                    if accepted:
                        return match
                    # canceled: continue polling

            self._draw()
            pygame.display.flip()
