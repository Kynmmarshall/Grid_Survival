import math
import sys

import pygame
import math

from audio import get_audio
from game import GameManager
from network import NetworkHost, NetworkClient, get_local_ip
from lan_prompts import prompt_host_or_join, prompt_ip_entry, toast_message
from host_waiting_screen import host_waiting_screen
from lan_prompts import draw_lan_backdrop, prompt_host_or_join, prompt_ip_entry
from network import NetworkClient, NetworkHost, get_local_ip
from scenes import ModeSelectionScreen, PlayerSelectionScreen, TitleScreen
from scenes.common import SceneAudioOverlay, _draw_rounded_rect, _load_font
from settings import (
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
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


def _wait_for_online_match_start(screen, clock, network, player_name: str, character_name: str):
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
                )
                return {
                    "players": players,
                    "local_player_index": 0,
                }

            if (not network.is_host) and message_type == "game_start":
                players = message.get("players") or []
                if not isinstance(players, list) or len(players) < 2:
                    continue
                return {
                    "players": players[:2],
                    "local_player_index": int(message.get("local_player_index", 1)),
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


def main():
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE, WINDOW_FLAGS)
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()

    while True:
        title_screen = TitleScreen(screen, clock)
        player_name = title_screen.run()
        if player_name is None:
            break

        while True:
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
                    # Show waiting/connected screen
                    ok = host_waiting_screen(screen, clock, host_ip, network)
                    if not ok:
                        toast_message(screen, clock, "Hosting cancelled.")
                        continue
                    local_player_index = 0
                else:
                    ip = prompt_ip_entry(screen, clock)
                    if not ip:
                        continue
                    network = NetworkClient()
                    connected = network.connect_to_host(ip)
                    if not connected:
                        toast_message(screen, clock, "Connection failed.")
                        continue
                    local_player_index = 1

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
                    )
                    if not match_setup:
                        network.disconnect()
                        break
                    selected_characters = [
                        str(player.get("character", selected_characters[0]))
                        for player in match_setup["players"]
                    ]
                    local_player_index = int(match_setup["local_player_index"])

                get_audio().stop_music(fade_ms=500)

                GameManager(
                    screen=screen,
                    clock=clock,
                    player_name=player_name,
                    game_mode=game_mode,
                    selected_characters=selected_characters,
                    network=network,
                    local_player_index=local_player_index,
                ).run()
                pygame.quit()
                return

    pygame.quit()


if __name__ == "__main__":
    main()
