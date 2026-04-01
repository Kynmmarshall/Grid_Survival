import pygame
import sys
from settings import (
    WINDOW_SIZE, MODE_CARD_WIDTH, MODE_CARD_HEIGHT, MODE_CARD_BASE_COLOR, MODE_CARD_HOVER_COLOR,
    MODE_CARD_BORDER_ONLINE_MP, MODE_CARD_HOVER_BORDER_ONLINE_MP, FONT_PATH_HEADING, FONT_PATH_BODY
)
from scenes.common import _draw_rounded_rect, _load_font

def host_waiting_screen(screen, clock, host_ip, network):
    width, height = WINDOW_SIZE
    font_title = _load_font(FONT_PATH_HEADING, 38, bold=True)
    font_body = _load_font(FONT_PATH_BODY, 24)
    font_small = _load_font(FONT_PATH_BODY, 18)
    info = f"Your IP: {host_ip}"
    connected = False
    client_addr = None
    while not connected:
        screen.fill((10, 14, 26))
        title = font_title.render("Waiting for player to join...", True, (255, 255, 255))
        screen.blit(title, (width // 2 - title.get_width() // 2, 120))
        info_surf = font_body.render(info, True, (180, 80, 255))
        screen.blit(info_surf, (width // 2 - info_surf.get_width() // 2, 200))
        hint = font_small.render("Press ESC to cancel", True, (170, 170, 170))
        screen.blit(hint, hint.get_rect(center=(width // 2, 240)))
        # Show connected devices (if any)
        if hasattr(network, 'socket') and network.socket:
            try:
                client_addr = network.socket.getpeername()
                connected = True
            except Exception:
                connected = False
        if connected:
            msg = f"Player connected: {client_addr[0]}"
            msg_surf = font_body.render(msg, True, (50, 220, 80))
            screen.blit(msg_surf, (width // 2 - msg_surf.get_width() // 2, 300))
        else:
            msg = "No players connected yet."
            msg_surf = font_small.render(msg, True, (200, 200, 200))
            screen.blit(msg_surf, (width // 2 - msg_surf.get_width() // 2, 300))
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
        clock.tick(30)
    # Briefly show success before continuing
    for _ in range(30):
        screen.fill((10, 14, 26))
        title = font_title.render("Player connected!", True, (50, 220, 80))
        screen.blit(title, (width // 2 - title.get_width() // 2, 160))
        info_surf = font_body.render(f"{client_addr[0]}", True, (180, 80, 255))
        screen.blit(info_surf, (width // 2 - info_surf.get_width() // 2, 220))
        pygame.display.flip()
        clock.tick(30)
    return True
