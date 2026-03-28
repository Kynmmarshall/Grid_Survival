import pygame
import sys
from settings import (
    WINDOW_SIZE, MODE_CARD_WIDTH, MODE_CARD_HEIGHT, MODE_CARD_BASE_COLOR, MODE_CARD_HOVER_COLOR,
    MODE_CARD_BORDER_ONLINE_MP, MODE_CARD_HOVER_BORDER_ONLINE_MP, FONT_PATH_HEADING, FONT_PATH_BODY,
    FONT_SIZE_HEADING, FONT_SIZE_BODY
)
from scenes.common import _draw_rounded_rect, _load_font

def prompt_host_or_join(screen, clock):
    options = ["Host a game", "Join a game"]
    selected = 0
    width, height = WINDOW_SIZE
    card_w, card_h = MODE_CARD_WIDTH, MODE_CARD_HEIGHT
    gap = 34
    total_h = len(options) * card_h + (len(options) - 1) * gap
    start_y = (height - total_h) // 2 + 60
    font_title = _load_font(FONT_PATH_HEADING, 38, bold=True)
    font_card = _load_font(FONT_PATH_HEADING, 24, bold=True)
    font_desc = _load_font(FONT_PATH_BODY, 18)
    cards = []
    for i, opt in enumerate(options):
        rect = pygame.Rect(0, start_y + (card_h + gap) * i, card_w, card_h)
        rect.centerx = width // 2
        cards.append(rect)
    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        hovered = None
        for i, rect in enumerate(cards):
            if rect.collidepoint(mouse_pos):
                hovered = i
        screen.fill((10, 14, 26))
        title = font_title.render("LAN MULTIPLAYER", True, (255, 255, 255))
        screen.blit(title, (width // 2 - title.get_width() // 2, 80))
        for i, rect in enumerate(cards):
            is_selected = (i == selected) or (i == hovered)
            bg_color = MODE_CARD_HOVER_COLOR if is_selected else MODE_CARD_BASE_COLOR
            border_color = MODE_CARD_HOVER_BORDER_ONLINE_MP if is_selected else MODE_CARD_BORDER_ONLINE_MP
            _draw_rounded_rect(screen, rect, bg_color, border_color, 3 if is_selected else 2, 16)
            label = font_card.render(options[i], True, border_color)
            label_rect = label.get_rect(center=(rect.centerx, rect.centery - 10))
            screen.blit(label, label_rect)
            desc = "Host a new LAN game for others to join" if i == 0 else "Join a LAN game by entering host's IP"
            desc_surf = font_desc.render(desc, True, (200, 200, 200))
            desc_rect = desc_surf.get_rect(center=(rect.centerx, rect.centery + 28))
            screen.blit(desc_surf, desc_rect)
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(options)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(options)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    return "host" if selected == 0 else "join"
                elif event.key == pygame.K_ESCAPE:
                    return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i, rect in enumerate(cards):
                    if rect.collidepoint(event.pos):
                        return "host" if i == 0 else "join"

def prompt_ip_entry(screen, clock):
    font = pygame.font.SysFont(None, 40)
    input_str = ""
    while True:
        screen.fill((20, 20, 40))
        prompt = font.render("Enter Host IP:", True, (255, 255, 255))
        screen.blit(prompt, (screen.get_width() // 2 - prompt.get_width() // 2, 120))
        input_surf = font.render(input_str + "_", True, (255, 255, 0))
        screen.blit(input_surf, (screen.get_width() // 2 - input_surf.get_width() // 2, 200))
        pygame.display.flip()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN and input_str:
                    return input_str
                elif event.key == pygame.K_BACKSPACE:
                    input_str = input_str[:-1]
                elif event.key == pygame.K_ESCAPE:
                    return None
                elif event.unicode and (event.unicode.isdigit() or event.unicode == "."):
                    input_str += event.unicode
