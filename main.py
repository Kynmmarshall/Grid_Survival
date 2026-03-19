import pygame

from game import GameManager
from scenes import ModeSelectionScreen, TitleScreen
from settings import WINDOW_SIZE, WINDOW_TITLE


def main():
    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption(WINDOW_TITLE)
    clock = pygame.time.Clock()

    title_screen = TitleScreen(screen, clock)
    player_name = title_screen.run()
    if player_name is None:
        pygame.quit()
        return

    mode_screen = ModeSelectionScreen(screen, clock, player_name)
    game_mode = mode_screen.run()
    if game_mode is None:
        pygame.quit()
        return

    # Stop menu music before gameplay starts.
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.fadeout(500)
    except pygame.error:
        pass

    GameManager(screen=screen, clock=clock, player_name=player_name, game_mode=game_mode).run()


if __name__ == "__main__":
    main()