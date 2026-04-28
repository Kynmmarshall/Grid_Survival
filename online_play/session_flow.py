"""Online setup flow orchestration for menus and pre-match sessions."""

from __future__ import annotations

import math
import sys
import threading
from dataclasses import dataclass
from typing import Any, Callable

import pygame

from backend.online_service import OnlineService
from host_waiting_screen import host_waiting_screen
from lan_prompts import (
    draw_lan_backdrop,
    prompt_discovered_host,
    prompt_host_or_join,
    prompt_ip_entry,
    toast_message,
)
from scenes.common import SceneAudioOverlay, _draw_rounded_rect, _load_font
from scenes import InternetLobbySetup, InternetPartyLobbyScreen
from settings import FONT_PATH_BODY, FONT_PATH_HEADING, WINDOW_SIZE

from .match_flow import (
    MatchSettings,
    MatchStartPayload,
    NetworkPlayerSetup,
    build_game_start_payload,
    build_player_setup_payload,
    parse_game_start_message,
    parse_player_setup_message,
)
from .internet_session import InternetSessionClient
from .session import NetworkClient, NetworkHost, get_local_ip, get_public_ip


@dataclass(slots=True)
class OnlineSessionSelection:
    network: Any
    local_player_index: int
    selected_level: Any
    selected_target_score: int
    selected_player_count: int = 2
    selected_characters: list[str] | None = None
    network_player_names: list[str] | None = None
    requires_match_start: bool = True


def prompt_online_route(screen, clock) -> str | None:
    """Choose between direct LAN/IP play and internet lobby flow."""
    audio_overlay = SceneAudioOverlay()
    selected = 0
    options = [
        ("direct", "LAN CONNECT", "Use host/discover/join IP."),
        ("internet", "INTERNET LOBBY", "Create lobbies + queue + match assignment."),
    ]

    while True:
        for event in pygame.event.get():
            if audio_overlay.handle_event(event):
                continue
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
                    return None
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return options[selected][0]
                elif event.key == pygame.K_1:
                    return options[0][0]
                elif event.key == pygame.K_2:
                    return options[1][0]
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                width, height = WINDOW_SIZE
                panel = pygame.Rect(0, 0, min(980, width - 120), 360)
                panel.center = (width // 2, height // 2)
                card_h = 110
                card_gap = 20
                for idx in range(len(options)):
                    rect = pygame.Rect(
                        panel.left + 34,
                        panel.top + 92 + idx * (card_h + card_gap),
                        panel.width - 68,
                        card_h,
                    )
                    if rect.collidepoint(event.pos):
                        return options[idx][0]

        width, height = WINDOW_SIZE
        font_title = _load_font(FONT_PATH_HEADING, 34, bold=True)
        font_body = _load_font(FONT_PATH_BODY, 22)
        font_small = _load_font(FONT_PATH_BODY, 18)

        anim_time = pygame.time.get_ticks() / 1000.0
        draw_lan_backdrop(screen, anim_time)

        panel = pygame.Rect(0, 0, min(980, width - 120), 360)
        panel.center = (width // 2, height // 2)
        _draw_rounded_rect(screen, panel, (18, 24, 42, 236), (140, 168, 222), 3, 20)

        title = font_title.render("ONLINE ROUTE", True, (248, 250, 255))
        subtitle = font_body.render(
            "Choose how this online session should connect.",
            True,
            (198, 212, 236),
        )
        screen.blit(title, title.get_rect(center=(panel.centerx, panel.top + 46)))
        screen.blit(subtitle, subtitle.get_rect(center=(panel.centerx, panel.top + 78)))

        card_h = 110
        card_gap = 20
        mouse_pos = pygame.mouse.get_pos()
        for idx, (_, label, desc) in enumerate(options):
            rect = pygame.Rect(
                panel.left + 34,
                panel.top + 92 + idx * (card_h + card_gap),
                panel.width - 68,
                card_h,
            )
            active = idx == selected or rect.collidepoint(mouse_pos)
            border = (186, 122, 255) if active else (106, 128, 170)
            bg = (38, 52, 86, 232) if active else (28, 38, 62, 224)
            _draw_rounded_rect(screen, rect, bg, border, 3 if active else 2, 14)

            label_s = font_body.render(label, True, (245, 248, 255))
            desc_s = font_small.render(desc, True, (188, 204, 232))
            screen.blit(label_s, label_s.get_rect(midleft=(rect.left + 18, rect.top + 34)))
            screen.blit(desc_s, desc_s.get_rect(midleft=(rect.left + 18, rect.top + 68)))

            key = font_small.render(f"[{idx + 1}]", True, border)
            screen.blit(key, key.get_rect(topright=(rect.right - 14, rect.top + 12)))

        footer = font_small.render("ENTER to confirm * ESC to back", True, (168, 186, 220))
        screen.blit(footer, footer.get_rect(center=(panel.centerx, panel.bottom - 20)))
        audio_overlay.draw(screen)
        pygame.display.flip()
        clock.tick(60)


def draw_lobby_panel(
    screen,
    title: str,
    lines: list[str],
    accent=(180, 80, 255),
    audio_overlay: SceneAudioOverlay | None = None,
) -> None:
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


def wait_for_online_match_start(
    screen,
    clock,
    network,
    player_name: str,
    character_name: str,
    selected_level_id: int,
    selected_target_score: int,
    selected_player_count: int = 2,
) -> dict[str, Any] | None:
    local_setup = NetworkPlayerSetup(name=player_name, character=character_name)
    audio_overlay = SceneAudioOverlay()
    if not network.send_message("player_setup", **build_player_setup_payload(local_setup)):
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
                peer_setup = parse_player_setup_message(
                    message,
                    default_name="Player 2",
                    default_character=character_name,
                )
                if peer_setup is None:
                    continue
                start_payload = MatchStartPayload(
                    players=[local_setup, peer_setup],
                    local_player_index=1,
                    settings=MatchSettings(
                        level_id=int(selected_level_id),
                        target_score=int(selected_target_score),
                    ),
                )
                network.send_message(
                    "game_start",
                    player_count=max(2, min(4, int(selected_player_count))),
                    **build_game_start_payload(start_payload),
                )
                return {
                    "players": [
                        build_player_setup_payload(player)
                        for player in start_payload.players
                    ],
                    "local_player_index": 0,
                    "level_id": int(selected_level_id),
                    "target_score": int(selected_target_score),
                    "player_count": max(2, min(4, int(selected_player_count))),
                }

            if (not network.is_host) and message_type == "game_start":
                game_start = parse_game_start_message(message)
                if game_start is None:
                    continue
                return {
                    "players": [
                        build_player_setup_payload(player)
                        for player in game_start.players
                    ],
                    "local_player_index": int(game_start.local_player_index),
                    "level_id": int(game_start.settings.level_id),
                    "target_score": int(game_start.settings.target_score),
                    "player_count": max(2, min(4, int(message.get("player_count", 2)))),
                }

        title = "PLAY OVER LAN" if network.is_host else "JOINING OVER LAN"
        peer_line = "Connected. Syncing character choices..."
        if network.peer_address:
            peer_line = f"Connected to {network.peer_address[0]}"
        draw_lobby_panel(
            screen,
            title,
            [
                f"{local_setup.name} selected {local_setup.character}",
                peer_line,
                "Press ESC to cancel and go back.",
            ],
            audio_overlay=audio_overlay,
        )
        clock.tick(30)


def _resolve_host_waiting_screen(
    screen,
    clock,
    network: NetworkHost,
) -> bool:
    host_ip = get_local_ip()
    public_ip_result: list[str | None] = [None]
    upnp_result: list[str | None] = [None]

    def _fetch_public_ip() -> None:
        public_ip_result[0] = get_public_ip(timeout=6.0)

    def _try_upnp() -> None:
        status = network.try_upnp_mapping()
        if status:
            upnp_result[0] = f"UPnP OK - port {network.port} opened automatically"
        else:
            upnp_result[0] = (
                f"UPnP unavailable - forward port {network.port} "
                "on your router for internet play"
            )

    threading.Thread(target=_fetch_public_ip, daemon=True).start()
    threading.Thread(target=_try_upnp, daemon=True).start()

    return host_waiting_screen(
        screen,
        clock,
        host_ip,
        network,
        public_ip=lambda: public_ip_result[0],
        upnp_status=lambda: upnp_result[0],
    )


def _run_host_level_selection(
    screen,
    clock,
    choose_player_count: Callable[[], int | None],
    choose_level: Callable[[], Any | None],
    choose_target_score: Callable[[], int | None],
) -> tuple[int | None, Any | None, int | None]:
    while True:
        selected_player_count = choose_player_count()
        if selected_player_count is None:
            return None, None, None
        selected_player_count = max(2, min(4, int(selected_player_count)))

        selected_level = choose_level()
        if selected_level is None:
            return None, None, None

        selected_target_score = choose_target_score()
        if selected_target_score is None:
            continue

        return (
            selected_player_count,
            selected_level,
            max(1, int(selected_target_score)),
        )


def _connect_internet_match(
    screen,
    clock,
    *,
    online_service: OnlineService,
    player_name: str,
    rating: int,
    choose_player_count: Callable[[], int | None],
    choose_level: Callable[[], Any | None],
    choose_target_score: Callable[[], int | None],
    choose_characters: Callable[[int], list[str] | None],
    resolve_level_option: Callable[[int], Any | None],
    toast: Callable[[Any, Any, str], None],
) -> OnlineSessionSelection | None:
    health = online_service.health()
    if not health.get("ok"):
        toast(
            screen,
            clock,
            f"Internet control-plane unavailable: {health.get('error', 'offline')}",
        )
        return None

    while True:
        selected_player_count = choose_player_count()
        if selected_player_count is None:
            return None
        selected_player_count = max(2, min(4, int(selected_player_count)))

        selected_level = choose_level()
        if selected_level is None:
            return None

        selected_target_score = choose_target_score()
        if selected_target_score is None:
            continue
        selected_target_score = max(1, int(selected_target_score))

        selected_characters = choose_characters(1)
        if not selected_characters:
            return None

        lobby_setup = InternetLobbySetup(
            player_name=player_name,
            character_name=str(selected_characters[0]),
            level_id=int(selected_level.level_id),
            target_score=int(selected_target_score),
            player_count=int(selected_player_count),
            rating=int(rating),
        )
        party_lobby = InternetPartyLobbyScreen(
            screen,
            clock,
            online_service,
            lobby_setup,
        )
        internet_match = party_lobby.run()
        if not internet_match:
            return None

        join_info = internet_match.get("join") if isinstance(internet_match.get("join"), dict) else {}
        endpoint = str(join_info.get("endpoint", "")).strip()
        token = str(join_info.get("token", "")).strip()
        if not endpoint or not token:
            toast(screen, clock, "Match assignment missing endpoint/token.")
            continue

        internet_network = InternetSessionClient()
        connected = internet_network.connect_to_match(
            endpoint=endpoint,
            token=token,
            player_name=player_name,
        )
        if not connected:
            toast(
                screen,
                clock,
                f"Match connect failed: {internet_network.last_error or 'unknown error'}",
            )
            continue

        assigned_players = internet_match.get("players") if isinstance(internet_match.get("players"), list) else []
        network_player_names: list[str] = []
        selected_chars_for_match: list[str] = []
        local_player_index = 0
        for idx, payload in enumerate(assigned_players[:2]):
            if not isinstance(payload, dict):
                payload = {}
            name = str(payload.get("name", f"Player {idx + 1}"))
            network_player_names.append(name)
            selected_chars_for_match.append(str(payload.get("character", selected_characters[0])))
            if name == player_name:
                local_player_index = idx

        while len(selected_chars_for_match) < 2:
            selected_chars_for_match.append(str(selected_characters[0]))
        while len(network_player_names) < 2:
            network_player_names.append(f"Player {len(network_player_names) + 1}")

        selected_level = (
            resolve_level_option(int(internet_match.get("map_id", selected_level.level_id)))
            or selected_level
        )
        selected_target_score = max(
            1,
            int(internet_match.get("target_score", selected_target_score)),
        )
        return OnlineSessionSelection(
            network=internet_network,
            local_player_index=local_player_index,
            selected_level=selected_level,
            selected_target_score=selected_target_score,
            selected_player_count=selected_player_count,
            selected_characters=selected_chars_for_match[:2],
            network_player_names=network_player_names[:2],
            requires_match_start=False,
        )


def run_online_session_setup(
    screen,
    clock,
    *,
    player_name: str,
    rating: int,
    choose_player_count: Callable[[], int | None],
    choose_level: Callable[[], Any | None],
    choose_target_score: Callable[[], int | None],
    choose_characters: Callable[[int], list[str] | None],
    resolve_level_option: Callable[[int], Any | None],
    toast: Callable[[Any, Any, str], None] = toast_message,
) -> OnlineSessionSelection | None:
    route = prompt_online_route(screen, clock)
    if route is None:
        return None

    if route == "internet":
        return _connect_internet_match(
            screen,
            clock,
            online_service=OnlineService.from_env(),
            player_name=player_name,
            rating=rating,
            choose_player_count=choose_player_count,
            choose_level=choose_level,
            choose_target_score=choose_target_score,
            choose_characters=choose_characters,
            resolve_level_option=resolve_level_option,
            toast=toast,
        )

    choice = prompt_host_or_join(screen, clock)
    if choice is None:
        return None

    if choice == "host":
        network = NetworkHost()
        if not network.start_hosting():
            toast(screen, clock, "Hosting failed.")
            return None

        ok = _resolve_host_waiting_screen(screen, clock, network)
        if not ok:
            network.disconnect()
            toast(screen, clock, "Hosting cancelled.")
            return None

        selected_player_count, selected_level, selected_target_score = _run_host_level_selection(
            screen,
            clock,
            choose_player_count,
            choose_level,
            choose_target_score,
        )
        if selected_level is None or selected_player_count is None:
            network.disconnect()
            return None
        return OnlineSessionSelection(
            network=network,
            local_player_index=0,
            selected_level=selected_level,
            selected_target_score=int(selected_target_score),
            selected_player_count=int(selected_player_count),
        )

    if choice == "discover":
        result = prompt_discovered_host(screen, clock)
        if not result:
            return None
        network = NetworkClient()
        connected = network.connect_to_host(result["address"], result["port"])
    else:
        ip = prompt_ip_entry(screen, clock)
        if not ip:
            return None
        network = NetworkClient()
        connected = network.connect_to_host(ip)

    if not connected:
        toast(screen, clock, f"Connection failed: {network.last_error or 'unknown error'}")
        return None

    selected_level = resolve_level_option(1)
    if selected_level is None:
        toast(screen, clock, "No levels available.")
        network.disconnect()
        return None

    return OnlineSessionSelection(
        network=network,
        local_player_index=1,
        selected_level=selected_level,
        selected_target_score=3,
        selected_player_count=2,
    )
