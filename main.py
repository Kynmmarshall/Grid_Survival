import math
import sys

import pygame

from backend.account_service import AccountService
from audio import get_audio
from game import GameManager
from host_waiting_screen import host_waiting_screen
from lan_prompts import (
    draw_lan_backdrop,
    prompt_discovered_host,
    prompt_host_or_join,
    prompt_ip_entry,
    toast_message,
)
from network import NetworkClient, NetworkHost, get_local_ip, get_public_ip
from scenes import (
    AccountPortalScreen,
    LevelSelectionScreen,
    ModeSelectionScreen,
    PlayerSelectionScreen,
    TargetScoreSelectionScreen,
)
from scenes.common import SceneAudioOverlay, _draw_rounded_rect, _load_font, set_online_status_service
from scenes.common import set_menu_sync_indicator_result, set_menu_sync_indicator_running
from scenes.level_selection import resolve_level_option
from settings import (
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    FONT_PATH_SMALL,
    MUSIC_PATH,
    MODE_CAMPAIGN,
    MODE_LOCAL_MULTIPLAYER,
    MODE_ONLINE_MULTIPLAYER,
    WINDOW_FLAGS,
    WINDOW_SIZE,
    WINDOW_TITLE,
)


def _draw_lobby_panel(
    screen,
    title: str,
    lines: list[str],
    accent=(180, 80, 255),
    audio_overlay: SceneAudioOverlay | None = None,
):
    width, height = WINDOW_SIZE
    font_title = _load_font(FONT_PATH_HEADING, 32, bold=True)
    font_body = _load_font(FONT_PATH_BODY, 24)
    font_small = _load_font(FONT_PATH_BODY, 18)

    anim_time = pygame.time.get_ticks() / 1000.0
    draw_lan_backdrop(screen, anim_time)
    panel = pygame.Rect(0, 0, min(900, width - 120), 300)
    panel.center = (width // 2, height // 2)
    pulse = 0.5 + 0.5 * math.sin(anim_time * 2.6)
    glow = pygame.Surface((panel.width + 24, panel.height + 24), pygame.SRCALPHA)
    pygame.draw.rect(
        glow,
        (accent[0], accent[1], accent[2], int(30 + 18 * pulse)),
        glow.get_rect(),
        border_radius=24,
    )
    screen.blit(glow, (panel.left - 12, panel.top - 12), special_flags=pygame.BLEND_ADD)
    _draw_rounded_rect(screen, panel, (20, 28, 48), accent, 3, 18)

    title_surf = font_title.render(title, True, (255, 255, 255))
    screen.blit(title_surf, title_surf.get_rect(center=(panel.centerx, panel.top + 48)))

    y = panel.top + 110
    for idx, line in enumerate(lines):
        font = font_body if idx < 2 else font_small
        color = accent if idx == 1 else (225, 230, 240)
        if idx == 0:
            color = (255, 255, 255)
        surf = font.render(line, True, color)
        screen.blit(surf, surf.get_rect(center=(panel.centerx, y)))
        y += 38 if idx < 2 else 30

    if audio_overlay is not None:
        audio_overlay.draw(screen)

    pygame.display.flip()


def _prompt_campaign_ranked_choice(screen, clock) -> bool | None:
    width, height = WINDOW_SIZE
    font_title = _load_font(FONT_PATH_HEADING, 38, bold=True)
    font_sub = _load_font(FONT_PATH_BODY, 24)
    font_label = _load_font(FONT_PATH_BODY, 26, bold=True)
    font_desc = _load_font(FONT_PATH_SMALL, 18)
    font_hint = _load_font(FONT_PATH_SMALL, 17)
    audio_overlay = SceneAudioOverlay()

    selected = 0
    anim_time = 0.0

    panel = pygame.Rect(0, 0, min(1080, width - 100), min(520, height - 120))
    panel.center = (width // 2, height // 2)

    card_w = (panel.width - 92) // 2
    card_h = 250
    card_y = panel.top + 166
    left_card = pygame.Rect(panel.left + 30, card_y, card_w, card_h)
    right_card = pygame.Rect(panel.left + 62 + card_w, card_y, card_w, card_h)

    cards = [
        {
            "rect": left_card,
            "label": "RANKED",
            "desc": "RR can increase or decrease based on match performance.",
            "accent": (245, 204, 105),
            "value": True,
            "icon": "RR",
        },
        {
            "rect": right_card,
            "label": "UNRANKED",
            "desc": "Practice freely. No RR change, but unranked stats are tracked.",
            "accent": (132, 214, 255),
            "value": False,
            "icon": "UR",
        },
    ]

    def _wrap_desc(text: str, max_width: int) -> list[str]:
        words = str(text).split()
        if not words:
            return [""]

        lines: list[str] = []
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if font_desc.size(candidate)[0] <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
        return lines

    while True:
        dt = clock.tick(60) / 1000.0
        anim_time += dt

        for event in pygame.event.get():
            if audio_overlay.handle_event(event):
                continue
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    return None
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    selected = 0
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    selected = 1
                elif event.key in (pygame.K_1, pygame.K_r):
                    return True
                elif event.key in (pygame.K_2, pygame.K_u):
                    return False
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return bool(cards[selected]["value"])
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for idx, card in enumerate(cards):
                    if card["rect"].collidepoint(event.pos):
                        selected = idx
                        return bool(card["value"])

        mouse_pos = pygame.mouse.get_pos()
        for idx, card in enumerate(cards):
            if card["rect"].collidepoint(mouse_pos):
                selected = idx

        draw_lan_backdrop(screen, anim_time)
        pulse = 0.5 + 0.5 * math.sin(anim_time * 2.2)
        glow = pygame.Surface((panel.width + 30, panel.height + 30), pygame.SRCALPHA)
        pygame.draw.rect(
            glow,
            (120, 180, 255, int(28 + 18 * pulse)),
            glow.get_rect(),
            border_radius=26,
        )
        screen.blit(glow, (panel.left - 15, panel.top - 15), special_flags=pygame.BLEND_ADD)
        _draw_rounded_rect(screen, panel, (14, 18, 34, 236), (122, 168, 224), 3, 20)

        title = font_title.render("CAMPAIGN MATCH TYPE", True, (245, 248, 255))
        subtitle = font_sub.render("Choose how this campaign match should be tracked.", True, (200, 216, 238))
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 56)))
        screen.blit(subtitle, subtitle.get_rect(center=(panel.centerx, panel.top + 94)))

        for idx, card in enumerate(cards):
            is_selected = idx == selected
            hover = card["rect"].collidepoint(mouse_pos)
            active = is_selected or hover
            bg = (36, 54, 88, 230) if active else (24, 36, 62, 224)
            border = card["accent"] if active else (92, 122, 170)
            border_w = 3 if active else 2
            _draw_rounded_rect(screen, card["rect"], bg, border, border_w, 14)

            icon_rect = pygame.Rect(card["rect"].left + 20, card["rect"].top + 20, 50, 38)
            _draw_rounded_rect(screen, icon_rect, (24, 34, 55, 235), border, 2, 8)
            icon_text = font_hint.render(str(card["icon"]), True, (242, 247, 255))
            screen.blit(icon_text, icon_text.get_rect(center=icon_rect.center))

            label = font_label.render(str(card["label"]), True, (245, 248, 255))
            screen.blit(label, label.get_rect(midleft=(icon_rect.right + 12, icon_rect.centery)))

            desc_lines = _wrap_desc(str(card["desc"]), card["rect"].width - 44)
            y = card["rect"].top + 84
            for line in desc_lines[:2]:
                if not line:
                    continue
                desc_surf = font_desc.render(line, True, (198, 214, 238))
                screen.blit(desc_surf, desc_surf.get_rect(midleft=(card["rect"].left + 22, y)))
                y += 26

            key_hint = "[1] Ranked" if idx == 0 else "[2] Unranked"
            hint_surf = font_hint.render(key_hint, True, border)
            screen.blit(hint_surf, hint_surf.get_rect(bottomright=(card["rect"].right - 14, card["rect"].bottom - 12)))

        footer = font_hint.render("LEFT/RIGHT or click to pick * ENTER confirms * ESC back", True, (170, 190, 220))
        screen.blit(footer, footer.get_rect(center=(panel.centerx, panel.bottom - 28)))
        audio_overlay.draw(screen)
        pygame.display.flip()


def _wait_for_online_match_start(
    screen,
    clock,
    network,
    player_name: str,
    character_name: str,
    selected_level_id: int,
    selected_target_score: int,
):
    local_setup = {"name": player_name, "character": character_name}
    audio_overlay = SceneAudioOverlay()
    if not network.send_message("player_setup", **local_setup):
        return None

    while True:
        if not network.connected:
            return None

        for event in pygame.event.get():
            if audio_overlay.handle_event(event):
                continue
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                network.send_message("disconnect")
                return None

        for message in network.get_messages():
            message_type = message.get("type")
            if message_type == "disconnect":
                return None

            if network.is_host and message_type == "player_setup":
                peer_setup = {
                    "name": str(message.get("name", "Player 2")),
                    "character": str(message.get("character", character_name)),
                }
                players = [local_setup, peer_setup]
                network.send_message(
                    "game_start",
                    players=players,
                    local_player_index=1,
                    level_id=int(selected_level_id),
                    target_score=int(selected_target_score),
                )
                return {
                    "players": players,
                    "local_player_index": 0,
                    "level_id": int(selected_level_id),
                    "target_score": int(selected_target_score),
                }

            if (not network.is_host) and message_type == "game_start":
                players = message.get("players") or []
                if not isinstance(players, list) or len(players) < 2:
                    continue
                return {
                    "players": players[:2],
                    "local_player_index": int(message.get("local_player_index", 1)),
                    "level_id": int(message.get("level_id", selected_level_id)),
                    "target_score": int(message.get("target_score", selected_target_score)),
                }

        title = "PLAY OVER LAN" if network.is_host else "JOINING OVER LAN"
        peer_line = "Connected. Syncing character choices..."
        if network.peer_address:
            peer_line = f"Connected to {network.peer_address[0]}"
        _draw_lobby_panel(
            screen,
            title,
            [
                f"{player_name} selected {character_name}",
                peer_line,
                "Press ESC to cancel and go back.",
            ],
            audio_overlay=audio_overlay,
        )
        clock.tick(30)


def _sync_account_in_menu(account_service: AccountService, username: str | None) -> None:
    """Run account sync only from menu flow (never during gameplay)."""
    if not username:
        return
    set_menu_sync_indicator_running()
    synced = False
    try:
        synced = bool(account_service.sync_pending(username))
    except Exception:
        synced = False
    set_menu_sync_indicator_result(synced)


def main():
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE, WINDOW_FLAGS)
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()
    account_service = AccountService()
    set_online_status_service(account_service)
    active_account_username = account_service.get_recent_account_username()

    while True:
        get_audio().play_music(track=MUSIC_PATH, loop=True, fade_ms=900)

        account_portal = AccountPortalScreen(
            screen,
            clock,
            account_service,
            suggested_username=active_account_username or "Player",
            current_username=active_account_username,
        )
        account_result = account_portal.run()
        if account_result.get("action") == "quit":
            pygame.quit()
            return
        if account_result.get("action") == "back":
            pygame.quit()
            return
        if account_result.get("action") != "continue":
            continue

        player_name = str(account_result.get("player_name") or active_account_username or "Player")
        active_account_username = account_result.get("account_username") or None
        _sync_account_in_menu(account_service, active_account_username)

        while True:
            break_to_title = False
            _sync_account_in_menu(account_service, active_account_username)
            mode_screen = ModeSelectionScreen(screen, clock, player_name)
            game_mode = mode_screen.run()
            if game_mode is None:
                if getattr(mode_screen, "quit_requested", False):
                    pygame.quit()
                    return
                break

            network = None
            local_player_index = 0
            num_players = 2 if game_mode == MODE_LOCAL_MULTIPLAYER else 1
            selected_level = None
            selected_target_score = 3
            network_player_names = None
            ranked_override = None

            if game_mode == MODE_CAMPAIGN:
                ranked_override = _prompt_campaign_ranked_choice(screen, clock)
                if ranked_override is None:
                    continue

            if game_mode == MODE_ONLINE_MULTIPLAYER:
                choice = prompt_host_or_join(screen, clock)
                if choice is None:
                    continue

                if choice == "host":
                    network = NetworkHost()
                    hosting = network.start_hosting()
                    if not hosting:
                        toast_message(screen, clock, "Hosting failed.")
                        continue

                    host_ip = get_local_ip()

                    # Fetch the public IP and try UPnP in background threads so
                    # the waiting screen renders immediately without freezing.
                    import threading as _threading

                    _pub_result: list[str | None] = [None]
                    _upnp_result: list[str | None] = [None]

                    def _fetch_public_ip():
                        _pub_result[0] = get_public_ip(timeout=6.0)

                    def _try_upnp():
                        status = network.try_upnp_mapping()
                        if status:
                            _upnp_result[0] = f"UPnP OK \u2013 port {network.port} opened automatically"
                        else:
                            _upnp_result[0] = (
                                f"UPnP unavailable \u2013 forward port {network.port} "
                                "on your router for internet play"
                            )

                    _threading.Thread(target=_fetch_public_ip, daemon=True).start()
                    _threading.Thread(target=_try_upnp, daemon=True).start()

                    # Pass lambdas so the waiting screen reads the latest value
                    # from the background threads on every display tick — the
                    # public IP and UPnP status appear as soon as they resolve.
                    ok = host_waiting_screen(
                        screen,
                        clock,
                        host_ip,
                        network,
                        public_ip=lambda: _pub_result[0],
                        upnp_status=lambda: _upnp_result[0],
                    )
                    if not ok:
                        # The host_waiting_screen already returned False; respect that.
                        if network:
                            network.disconnect()
                        toast_message(screen, clock, "Hosting cancelled.")
                        network = None
                        continue

                    local_player_index = 0

                elif choice == "discover":
                    # LAN auto-discovery: scan for broadcasting hosts.
                    result = prompt_discovered_host(screen, clock)
                    if not result:
                        continue
                    network = NetworkClient()
                    connected = network.connect_to_host(result["address"], result["port"])
                    if not connected:
                        toast_message(screen, clock, f"Connection failed: {network.last_error or 'unknown error'}")
                        continue
                    local_player_index = 1

                else:  # join_ip — manual entry, works for both LAN and internet
                    ip = prompt_ip_entry(screen, clock)
                    if not ip:
                        continue
                    network = NetworkClient()
                    connected = network.connect_to_host(ip)
                    if not connected:
                        toast_message(screen, clock, f"Connection failed: {network.last_error or 'unknown error'}")
                        continue
                    local_player_index = 1

                if choice == "host":
                    while True:
                        level_screen = LevelSelectionScreen(screen, clock, game_mode)
                        selected_level = level_screen.run()
                        if selected_level is None:
                            if getattr(level_screen, "quit_requested", False):
                                pygame.quit()
                                return
                            if network:
                                network.disconnect()
                            break

                        target_score_screen = TargetScoreSelectionScreen(screen, clock)
                        selected_target_score = target_score_screen.run()
                        if selected_target_score is None:
                            if getattr(target_score_screen, "quit_requested", False):
                                pygame.quit()
                                return
                            continue

                        selected_target_score = max(1, int(selected_target_score))
                        break

                    if selected_level is None:
                        continue
                else:
                    selected_level = resolve_level_option(1)
                    if selected_level is None:
                        toast_message(screen, clock, "No levels available.")
                        if network:
                            network.disconnect()
                        continue
            else:
                while True:
                    level_screen = LevelSelectionScreen(screen, clock, game_mode)
                    selected_level = level_screen.run()
                    if selected_level is None:
                        if getattr(level_screen, "quit_requested", False):
                            pygame.quit()
                            return
                        break

                    target_score_screen = TargetScoreSelectionScreen(screen, clock)
                    selected_target_score = target_score_screen.run()
                    if selected_target_score is None:
                        if getattr(target_score_screen, "quit_requested", False):
                            pygame.quit()
                            return
                        continue

                    selected_target_score = max(1, int(selected_target_score))
                    break

                if selected_level is None:
                    continue

            while True:
                char_select = PlayerSelectionScreen(
                    screen,
                    clock,
                    game_mode,
                    num_players=num_players,
                )
                selected_characters = char_select.run()
                if not selected_characters:
                    if getattr(char_select, "quit_requested", False):
                        pygame.quit()
                        return
                    if network:
                        network.disconnect()
                    break

                if game_mode == MODE_ONLINE_MULTIPLAYER:
                    match_setup = _wait_for_online_match_start(
                        screen,
                        clock,
                        network,
                        player_name,
                        selected_characters[0],
                        selected_level.level_id,
                        selected_target_score,
                    )
                    if not match_setup:
                        network.disconnect()
                        break
                    selected_characters = [
                        str(player.get("character", selected_characters[0]))
                        for player in match_setup["players"]
                    ]
                    network_player_names = [
                        str(player.get("name", f"Player {idx + 1}"))
                        for idx, player in enumerate(match_setup["players"])
                    ]
                    local_player_index = int(match_setup["local_player_index"])
                    selected_level = resolve_level_option(
                        int(match_setup.get("level_id", selected_level.level_id))
                    ) or selected_level
                    selected_target_score = max(
                        1,
                        int(match_setup.get("target_score", selected_target_score)),
                    )

                get_audio().stop_music(fade_ms=500)

                result = GameManager(
                    screen=screen,
                    clock=clock,
                    player_name=player_name,
                    game_mode=game_mode,
                    selected_characters=selected_characters,
                    network=network,
                    local_player_index=local_player_index,
                    level_map_path=selected_level.map_path,
                    level_background_path=selected_level.background_path,
                    target_score=selected_target_score,
                    account_service=account_service,
                    account_username=active_account_username,
                    network_player_names=network_player_names,
                    ranked_override=ranked_override,
                ).run()
                
                if result == "main_menu":
                    _sync_account_in_menu(account_service, active_account_username)
                    break_to_title = True
                    break
                else:
                    pygame.quit()
                    return

            if break_to_title:
                break

    pygame.quit()


if __name__ == "__main__":
    main()
