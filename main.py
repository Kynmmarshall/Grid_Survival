import pygame
from audio import get_audio
from game import GameManager
from network import NetworkHost, NetworkClient, get_local_ip
from lan_prompts import prompt_host_or_join, prompt_ip_entry, toast_message
from host_waiting_screen import host_waiting_screen
from scenes import ModeSelectionScreen, TitleScreen, PlayerSelectionScreen
from settings import MODE_LOCAL_MULTIPLAYER, MODE_ONLINE_MULTIPLAYER, WINDOW_SIZE, WINDOW_TITLE



def main():
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
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
                # Back to title screen to edit the name or exit
                break


            if game_mode == MODE_ONLINE_MULTIPLAYER:
                # LAN Multiplayer: prompt host/join
                choice = prompt_host_or_join(screen, clock)
                if choice is None:
                    continue  # Back to mode selection
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
                else:
                    ip = prompt_ip_entry(screen, clock)
                    if not ip:
                        continue
                    network = NetworkClient()
                    connected = network.connect_to_host(ip)
                    if not connected:
                        toast_message(screen, clock, "Connection failed.")
                        continue
                num_players = 2
            else:
                network = None
                num_players = 2 if game_mode == MODE_LOCAL_MULTIPLAYER else 1

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
                    # Back to mode selection
                    break

                # Stop menu music before gameplay starts so gameplay can control audio.
                get_audio().stop_music(fade_ms=500)

                GameManager(
                    screen=screen,
                    clock=clock,
                    player_name=player_name,
                    game_mode=game_mode,
                    selected_characters=selected_characters,
                    network=network
                ).run()
                pygame.quit()
                return

    pygame.quit()


if __name__ == "__main__":
    main()