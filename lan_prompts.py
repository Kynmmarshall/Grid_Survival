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
    width, height = WINDOW_SIZE
    card_w, card_h = MODE_CARD_WIDTH, MODE_CARD_HEIGHT
    font_title = _load_font(FONT_PATH_HEADING, 32, bold=True)
    font_body = _load_font(FONT_PATH_BODY, 22)
    font_small = _load_font(FONT_PATH_BODY, 18)
    input_str = ""
    btn_w, btn_h = 160, 50
    btn_gap = 20
    card_rect = pygame.Rect(0, 0, card_w, card_h)
    card_rect.center = (width // 2, height // 2)
    btn_confirm = pygame.Rect(0, 0, btn_w, btn_h)
    btn_back = pygame.Rect(0, 0, btn_w, btn_h)
    btn_confirm.center = (width // 2 + btn_w // 2 + btn_gap // 2, card_rect.bottom + 40)
    btn_back.center = (width // 2 - btn_w // 2 - btn_gap // 2, card_rect.bottom + 40)

    def draw(show_cursor=True):
        screen.fill((10, 14, 26))
        _draw_rounded_rect(screen, card_rect, MODE_CARD_BASE_COLOR, MODE_CARD_BORDER_ONLINE_MP, 2, 18)
        title = font_title.render("Enter Host IP", True, (255, 255, 255))
        screen.blit(title, title.get_rect(center=(card_rect.centerx, card_rect.top + 28)))
        prompt = font_small.render("Type the host machine's IP and press Enter", True, (200, 200, 200))
        screen.blit(prompt, prompt.get_rect(center=(card_rect.centerx, card_rect.top + 60)))
        ip_display = input_str + ("_" if show_cursor else "")
        ip_surf = font_body.render(ip_display, True, (255, 220, 90))
        screen.blit(ip_surf, ip_surf.get_rect(center=(card_rect.centerx, card_rect.centery + 6)))
        # buttons
        mouse_pos = pygame.mouse.get_pos()
        for rect, label in ((btn_back, "Back"), (btn_confirm, "Connect")):
            hovered = rect.collidepoint(mouse_pos)
            bg = MODE_CARD_HOVER_COLOR if hovered else MODE_CARD_BASE_COLOR
            border = MODE_CARD_HOVER_BORDER_ONLINE_MP if hovered else MODE_CARD_BORDER_ONLINE_MP
            _draw_rounded_rect(screen, rect, bg, border, 2 if not hovered else 3, 14)
            txt = font_body.render(label, True, border)
            screen.blit(txt, txt.get_rect(center=rect.center))
        pygame.display.flip()

    cursor_timer = 0.0
    while True:
        dt = clock.tick(60) / 1000.0
        cursor_timer += dt
        show_cursor = (int(cursor_timer * 2) % 2) == 0
        draw(show_cursor)
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
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_confirm.collidepoint(event.pos) and input_str:
                    return input_str
                if btn_back.collidepoint(event.pos):
                    return None


def toast_message(screen, clock, message: str, color=(255, 120, 120), duration: float = 1.4):
    font = pygame.font.SysFont(None, 32)
    elapsed = 0.0
    overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
    while elapsed < duration:
        dt = clock.tick(60) / 1000.0
        elapsed += dt
        overlay.fill((0, 0, 0, 0))
        text = font.render(message, True, color)
        bg_rect = text.get_rect(center=(WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2))
        bg_rect.inflate_ip(24, 16)
        pygame.draw.rect(overlay, (20, 20, 30, 210), bg_rect, border_radius=10)
        pygame.draw.rect(overlay, (color[0], color[1], color[2], 220), bg_rect, width=2, border_radius=10)
        overlay.blit(text, text.get_rect(center=bg_rect.center))
        screen.blit(overlay, (0, 0))
        pygame.display.flip()
