import math
import sys

import pygame

from online_play import LanGameFinder
from scenes.common import SceneAudioOverlay, _draw_rounded_rect, _load_font
from settings import (
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    FONT_PATH_SMALL,
    FONT_SIZE_BODY,
    FONT_SIZE_HEADING,
    FONT_SIZE_SMALL,
    MODE_BG_COLOR,
    MODE_BG_IMAGE_PATH,
    MODE_CARD_BASE_COLOR,
    MODE_CARD_BORDER_ONLINE_MP,
    MODE_CARD_HEIGHT,
    MODE_CARD_HOVER_BORDER_ONLINE_MP,
    MODE_CARD_HOVER_COLOR,
    MODE_CARD_WIDTH,
    SCENE_FADE_SPEED,
    SCENE_OVERLAY_COLOR,
    TARGET_FPS,
    WINDOW_SIZE,
)


_LAN_BG_CACHE = None


def _load_lan_background():
    global _LAN_BG_CACHE
    if _LAN_BG_CACHE is not None:
        return _LAN_BG_CACHE
    if MODE_BG_IMAGE_PATH.exists():
        try:
            raw_bg = pygame.image.load(str(MODE_BG_IMAGE_PATH)).convert()
            width, height = WINDOW_SIZE
            img_w, img_h = raw_bg.get_size()
            scale = max(width / img_w, height / img_h)
            scaled = pygame.transform.smoothscale(
                raw_bg,
                (int(img_w * scale), int(img_h * scale)),
            )
            crop_x = max(0, (scaled.get_width() - width) // 2)
            crop_y = max(0, (scaled.get_height() - height) // 2)
            _LAN_BG_CACHE = scaled.subsurface((crop_x, crop_y, width, height)).copy()
            return _LAN_BG_CACHE
        except Exception:
            _LAN_BG_CACHE = False
            return None
    _LAN_BG_CACHE = False
    return None


def draw_lan_backdrop(screen, anim_time: float = 0.0):
    background = _load_lan_background()
    if background:
        screen.blit(background, (0, 0))
        overlay = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)
        overlay.fill((8, 10, 22, 150))
        screen.blit(overlay, (0, 0))
    else:
        screen.fill(MODE_BG_COLOR)

    width, height = WINDOW_SIZE
    glow = pygame.Surface((width, height), pygame.SRCALPHA)
    pulse = 0.5 + 0.5 * math.sin(anim_time * 1.4)
    pygame.draw.circle(
        glow,
        (120, 90, 255, int(28 + 18 * pulse)),
        (width // 2, height // 3),
        min(width, height) // 3,
    )
    pygame.draw.circle(
        glow,
        (70, 180, 255, int(20 + 10 * (1.0 - pulse))),
        (width // 2, int(height * 0.78)),
        min(width, height) // 4,
    )
    screen.blit(glow, (0, 0), special_flags=pygame.BLEND_ADD)


def _fade(screen, clock, draw_frame, fade_in: bool):
    overlay = pygame.Surface(WINDOW_SIZE)
    alpha = 255 if fade_in else 0
    local_time = 0.0

    while True:
        dt = clock.tick(TARGET_FPS) / 1000.0
        local_time += dt
        step = SCENE_FADE_SPEED * dt
        if fade_in:
            alpha -= step
            if alpha <= 0:
                break
        else:
            alpha += step
            if alpha >= 255:
                alpha = 255
                break

        draw_frame(local_time)
        overlay.fill(SCENE_OVERLAY_COLOR)
        overlay.set_alpha(int(alpha))
        screen.blit(overlay, (0, 0))
        pygame.display.flip()


def _wrap_text(font: pygame.font.Font, text: str, max_width: int) -> list[str]:
    words = text.split()
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


def prompt_host_or_join(screen, clock):
    options = [
        {
            "value": "host",
            "title": "HOST GAME",
            "desc": "Open a match for players on your LAN or anywhere on the internet.",
            "hint": "Your LAN IP and public IP will both be displayed.",
        },
        {
            "value": "discover",
            "title": "FIND GAMES ON LAN",
            "desc": "Scan for visible hosts on the same Wi-Fi or router.",
            "hint": "Choose a visible machine instead of typing an IP.",
        },
        {
            "value": "join_ip",
            "title": "JOIN BY IP",
            "desc": "Connect to any host using their IP address.",
            "hint": "Works on LAN (local IP) or over the internet (public IP).",
        },
    ]

    width, height = WINDOW_SIZE
    font_header = _load_font(FONT_PATH_HEADING, FONT_SIZE_HEADING + 10, bold=True)
    font_title = _load_font(FONT_PATH_HEADING, 30, bold=True)
    font_body = _load_font(FONT_PATH_BODY, max(FONT_SIZE_BODY + 2, 24))
    font_small = _load_font(FONT_PATH_SMALL, max(FONT_SIZE_SMALL + 2, 20))
    audio_overlay = SceneAudioOverlay()

    selected = 0
    anim_time = 0.0
    header_offset = 80.0
    cards = []
    card_w = min(max(MODE_CARD_WIDTH + 170, 620), width - 120)
    card_h = max(MODE_CARD_HEIGHT + 46, 160)
    gap = 42
    total_h = len(options) * card_h + (len(options) - 1) * gap
    start_y = (height - total_h) // 2 + 92

    for idx, option in enumerate(options):
        rect = pygame.Rect(
            0,
            start_y + idx * (card_h + gap),
            card_w,
            card_h,
        )
        rect.centerx = width // 2
        cards.append(
            {
                "option": option,
                "rect": rect,
                "hover_y": 0.0,
                "click_timer": 0.0,
            }
        )

    def draw_frame(local_time: float):
        nonlocal header_offset
        draw_lan_backdrop(screen, anim_time + local_time)
        progress = min(1.0, (anim_time + local_time) / 0.65)
        eased = 1.0 - (1.0 - progress) ** 3
        header_offset = 80.0 * (1.0 - eased)

        title = font_header.render("PLAY ONLINE", True, (255, 255, 255))
        subtitle = font_body.render(
            "Host on your LAN or invite anyone over the internet.",
            True,
            (205, 210, 225),
        )
        screen.blit(title, title.get_rect(center=(width // 2, int(86 + header_offset))))
        screen.blit(subtitle, subtitle.get_rect(center=(width // 2, int(152 + header_offset))))

        mouse_pos = pygame.mouse.get_pos()
        for idx, card in enumerate(cards):
            rect = card["rect"].copy()
            hovered = rect.collidepoint(mouse_pos)
            target_y = -6.0 if hovered or idx == selected else 0.0
            card["hover_y"] += (target_y - card["hover_y"]) * 0.22
            rect.y += int(card["hover_y"])

            if card["click_timer"] > 0:
                card["click_timer"] = max(0.0, card["click_timer"] - 1 / TARGET_FPS)
            scale = 1.0 - 0.04 * (card["click_timer"] / 0.12) if card["click_timer"] > 0 else 1.0
            if scale != 1.0:
                rect = pygame.Rect(
                    rect.centerx - int(rect.width * scale) // 2,
                    rect.centery - int(rect.height * scale) // 2,
                    int(rect.width * scale),
                    int(rect.height * scale),
                )

            active = hovered or idx == selected
            bg = MODE_CARD_HOVER_COLOR if active else MODE_CARD_BASE_COLOR
            border = MODE_CARD_HOVER_BORDER_ONLINE_MP if active else MODE_CARD_BORDER_ONLINE_MP

            pulse = 0.5 + 0.5 * math.sin((anim_time + local_time) * 3.5 + idx)
            if active:
                glow = pygame.Surface((rect.width + 20, rect.height + 20), pygame.SRCALPHA)
                pygame.draw.rect(
                    glow,
                    (border[0], border[1], border[2], int(34 + 24 * pulse)),
                    glow.get_rect(),
                    border_radius=20,
                )
                screen.blit(glow, (rect.left - 10, rect.top - 10), special_flags=pygame.BLEND_ADD)

            _draw_rounded_rect(screen, rect, bg, border, 3 if active else 2, 16)

            title_surf = font_title.render(
                card["option"]["title"],
                True,
                border if active else (255, 255, 255),
            )
            max_text_width = rect.width - 48
            desc_lines = _wrap_text(font_body, card["option"]["desc"], max_text_width)
            hint_lines = _wrap_text(font_small, card["option"]["hint"], max_text_width)

            screen.blit(title_surf, title_surf.get_rect(midtop=(rect.centerx, rect.top + 14)))

            line_y = rect.top + 62
            for line in desc_lines[:2]:
                desc_surf = font_body.render(line, True, (215, 220, 235))
                screen.blit(desc_surf, desc_surf.get_rect(midtop=(rect.centerx, line_y)))
                line_y += font_body.get_height() + 2

            line_y += 6
            for line in hint_lines[:2]:
                hint_surf = font_small.render(line, True, (160, 175, 210))
                screen.blit(hint_surf, hint_surf.get_rect(midtop=(rect.centerx, line_y)))
                line_y += font_small.get_height() + 1

        footer = font_small.render("ENTER to confirm  *  ESC to go back", True, (175, 185, 205))
        screen.blit(footer, footer.get_rect(center=(width // 2, height - 44)))
        audio_overlay.draw(screen)

    _fade(screen, clock, draw_frame, fade_in=True)

    while True:
        dt = clock.tick(TARGET_FPS) / 1000.0
        anim_time += dt
        draw_frame(0.0)
        pygame.display.flip()

        for event in pygame.event.get():
            if audio_overlay.handle_event(event):
                continue
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(cards)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(cards)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    cards[selected]["click_timer"] = 0.12
                    draw_frame(0.0)
                    pygame.display.flip()
                    return cards[selected]["option"]["value"]
                elif event.key == pygame.K_ESCAPE:
                    return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for idx, card in enumerate(cards):
                    hover_rect = card["rect"].copy()
                    hover_rect.y += int(card["hover_y"])
                    if hover_rect.collidepoint(event.pos):
                        selected = idx
                        card["click_timer"] = 0.12
                        draw_frame(0.0)
                        pygame.display.flip()
                        return card["option"]["value"]


def prompt_discovered_host(screen, clock):
    width, height = WINDOW_SIZE
    font_header = _load_font(FONT_PATH_HEADING, FONT_SIZE_HEADING + 8, bold=True)
    font_body = _load_font(FONT_PATH_BODY, FONT_SIZE_BODY + 2)
    font_small = _load_font(FONT_PATH_SMALL, FONT_SIZE_SMALL + 2)
    font_title = _load_font(FONT_PATH_HEADING, 30, bold=True)
    audio_overlay = SceneAudioOverlay()

    finder = LanGameFinder()
    if not finder.start():
        return None

    anim_time = 0.0
    header_offset = 70.0
    probe_timer = 0.0
    selected = 0
    host_rects = []

    def draw_frame(local_time: float, hosts):
        nonlocal header_offset
        total_time = anim_time + local_time
        draw_lan_backdrop(screen, total_time)
        progress = min(1.0, total_time / 0.65)
        eased = 1.0 - (1.0 - progress) ** 3
        header_offset = 70.0 * (1.0 - eased)

        title = font_header.render("FIND GAMES ON LAN", True, (255, 255, 255))
        subtitle = font_body.render(
            "Visible hosts on this local network appear below.",
            True,
            (205, 210, 225),
        )
        screen.blit(title, title.get_rect(center=(width // 2, int(94 + header_offset))))
        screen.blit(subtitle, subtitle.get_rect(center=(width // 2, int(154 + header_offset))))

        host_rects.clear()
        list_top = int(height * 0.31)
        list_width = min(1050, width - 110)
        list_x = width // 2 - list_width // 2
        mouse_pos = pygame.mouse.get_pos()

        if hosts:
            card_height = 112
            gap = 20
            for idx, host in enumerate(hosts[:4]):
                rect = pygame.Rect(list_x, list_top + idx * (card_height + gap), list_width, card_height)
                hovered = rect.collidepoint(mouse_pos)
                active = hovered or idx == selected
                border = MODE_CARD_HOVER_BORDER_ONLINE_MP if active else MODE_CARD_BORDER_ONLINE_MP
                bg = MODE_CARD_HOVER_COLOR if active else MODE_CARD_BASE_COLOR
                pulse = 0.5 + 0.5 * math.sin(total_time * 3.0 + idx)
                if active:
                    glow = pygame.Surface((rect.width + 18, rect.height + 18), pygame.SRCALPHA)
                    pygame.draw.rect(
                        glow,
                        (border[0], border[1], border[2], int(28 + 18 * pulse)),
                        glow.get_rect(),
                        border_radius=20,
                    )
                    screen.blit(glow, (rect.left - 9, rect.top - 9), special_flags=pygame.BLEND_ADD)
                _draw_rounded_rect(screen, rect, bg, border, 3 if active else 2, 16)

                title_surf = font_title.render(host.host_name.upper(), True, border if active else (255, 255, 255))
                machine_surf = font_body.render(host.machine_name, True, (220, 225, 235))
                address_surf = font_small.render(f"{host.address}:{host.port}", True, (165, 175, 205))
                screen.blit(title_surf, title_surf.get_rect(topleft=(rect.left + 28, rect.top + 14)))
                screen.blit(machine_surf, machine_surf.get_rect(topleft=(rect.left + 28, rect.top + 58)))
                screen.blit(address_surf, address_surf.get_rect(topright=(rect.right - 28, rect.top + 24)))
                host_rects.append((rect, host))
        else:
            panel = pygame.Rect(0, 0, min(940, width - 140), 238)
            panel.center = (width // 2, int(height * 0.58))
            pulse = 0.5 + 0.5 * math.sin(total_time * 3.0)
            glow = pygame.Surface((panel.width + 24, panel.height + 24), pygame.SRCALPHA)
            pygame.draw.rect(
                glow,
                (180, 80, 255, int(30 + 22 * pulse)),
                glow.get_rect(),
                border_radius=24,
            )
            screen.blit(glow, (panel.left - 12, panel.top - 12), special_flags=pygame.BLEND_ADD)
            _draw_rounded_rect(screen, panel, (24, 32, 54), MODE_CARD_BORDER_ONLINE_MP, 3, 18)

            spinner = "." * (1 + (int(total_time * 3.5) % 3))
            waiting = font_title.render(f"SCANNING FOR HOSTS{spinner}", True, (255, 255, 255))
            helper = font_body.render("Make sure another player already chose Host Game.", True, (210, 220, 240))
            tip = font_small.render("Press R to refresh or ESC to go back.", True, (165, 175, 205))
            screen.blit(waiting, waiting.get_rect(center=(panel.centerx, panel.top + 74)))
            screen.blit(helper, helper.get_rect(center=(panel.centerx, panel.top + 130)))
            screen.blit(tip, tip.get_rect(center=(panel.centerx, panel.top + 176)))

        helper = font_small.render(
            "Hosts are discovered automatically on the same local network.",
            True,
            (165, 175, 205),
        )
        footer = font_small.render("ENTER to connect  *  R to rescan  *  ESC to go back", True, (175, 185, 205))
        screen.blit(helper, helper.get_rect(center=(width // 2, height - 70)))
        screen.blit(footer, footer.get_rect(center=(width // 2, height - 44)))
        audio_overlay.draw(screen)

    try:
        _fade(screen, clock, lambda local_time: draw_frame(local_time, finder.poll_hosts()), fade_in=True)

        while True:
            dt = clock.tick(TARGET_FPS) / 1000.0
            anim_time += dt
            probe_timer += dt
            if probe_timer >= 1.0:
                finder.probe()
                probe_timer = 0.0

            hosts = finder.poll_hosts()
            visible_hosts = hosts[:4]
            if selected >= len(visible_hosts):
                selected = max(0, len(visible_hosts) - 1)

            draw_frame(0.0, visible_hosts)
            pygame.display.flip()

            for event in pygame.event.get():
                if audio_overlay.handle_event(event):
                    continue
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_UP, pygame.K_w) and visible_hosts:
                        selected = (selected - 1) % len(visible_hosts)
                    elif event.key in (pygame.K_DOWN, pygame.K_s) and visible_hosts:
                        selected = (selected + 1) % len(visible_hosts)
                    elif event.key == pygame.K_r:
                        finder.probe()
                        probe_timer = 0.0
                    elif event.key == pygame.K_RETURN and visible_hosts:
                        host = visible_hosts[selected]
                        return {
                            "host_name": host.host_name,
                            "machine_name": host.machine_name,
                            "address": host.address,
                            "port": host.port,
                        }
                    elif event.key == pygame.K_ESCAPE:
                        return None
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    for rect, host in host_rects:
                        if rect.collidepoint(event.pos):
                            return {
                                "host_name": host.host_name,
                                "machine_name": host.machine_name,
                                "address": host.address,
                                "port": host.port,
                            }
    finally:
        finder.close()


def prompt_ip_entry(screen, clock):
    width, height = WINDOW_SIZE
    card_w = min(max(MODE_CARD_WIDTH + 180, 640), width - 120)
    card_h = max(MODE_CARD_HEIGHT + 110, 230)
    font_title = _load_font(FONT_PATH_HEADING, 40, bold=True)
    font_body = _load_font(FONT_PATH_BODY, 32)
    font_small = _load_font(FONT_PATH_BODY, 22)
    font_button = _load_font(FONT_PATH_BODY, 24)
    audio_overlay = SceneAudioOverlay()
    input_str = ""
    btn_w, btn_h = 200, 58
    btn_gap = 20
    card_rect = pygame.Rect(0, 0, card_w, card_h)
    card_rect.center = (width // 2, height // 2 + 10)
    btn_confirm = pygame.Rect(0, 0, btn_w, btn_h)
    btn_back = pygame.Rect(0, 0, btn_w, btn_h)
    btn_confirm.center = (width // 2 + btn_w // 2 + btn_gap // 2, card_rect.bottom + 52)
    btn_back.center = (width // 2 - btn_w // 2 - btn_gap // 2, card_rect.bottom + 52)

    def draw(show_cursor=True, local_time: float = 0.0):
        draw_lan_backdrop(screen, local_time)
        _draw_rounded_rect(screen, card_rect, MODE_CARD_BASE_COLOR, MODE_CARD_BORDER_ONLINE_MP, 3, 20)
        title = font_title.render("Enter Host IP", True, (255, 255, 255))
        screen.blit(title, title.get_rect(center=(card_rect.centerx, card_rect.top + 42)))

        help_lines = _wrap_text(
            font_small,
            "LAN IP (e.g. 192.168.x.x) or Public IP for internet play",
            card_rect.width - 84,
        )
        help_y = card_rect.top + 86
        for line in help_lines[:2]:
            prompt = font_small.render(line, True, (200, 205, 220))
            screen.blit(prompt, prompt.get_rect(center=(card_rect.centerx, help_y)))
            help_y += font_small.get_height() + 2

        input_box = pygame.Rect(card_rect.left + 52, card_rect.centery - 6, card_rect.width - 104, 62)
        _draw_rounded_rect(screen, input_box, (16, 24, 44), MODE_CARD_BORDER_ONLINE_MP, 2, 14)
        ip_display = input_str + ("_" if show_cursor else "")
        ip_surf = font_body.render(ip_display, True, (255, 220, 90))
        ip_rect = ip_surf.get_rect(midleft=(input_box.left + 16, input_box.centery + 1))
        screen.blit(ip_surf, ip_rect)

        tip = font_small.render("Digits and dots only", True, (165, 175, 205))
        screen.blit(tip, tip.get_rect(center=(card_rect.centerx, input_box.bottom + 22)))

        # buttons
        mouse_pos = pygame.mouse.get_pos()
        for rect, label in ((btn_back, "Back"), (btn_confirm, "Connect")):
            hovered = rect.collidepoint(mouse_pos)
            bg = MODE_CARD_HOVER_COLOR if hovered else MODE_CARD_BASE_COLOR
            border = MODE_CARD_HOVER_BORDER_ONLINE_MP if hovered else MODE_CARD_BORDER_ONLINE_MP
            _draw_rounded_rect(screen, rect, bg, border, 2 if not hovered else 3, 16)
            txt = font_button.render(label.upper(), True, border)
            screen.blit(txt, txt.get_rect(center=rect.center))

        footer = font_small.render("ENTER to connect  *  ESC to go back", True, (175, 185, 205))
        screen.blit(footer, footer.get_rect(center=(width // 2, height - 44)))
        audio_overlay.draw(screen)
        pygame.display.flip()

    cursor_timer = 0.0
    while True:
        dt = clock.tick(60) / 1000.0
        cursor_timer += dt
        show_cursor = (int(cursor_timer * 2) % 2) == 0
        draw(show_cursor, cursor_timer)
        for event in pygame.event.get():
            if audio_overlay.handle_event(event):
                continue
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
                elif event.unicode and (event.unicode.isdigit() or event.unicode == ".") and len(input_str) < 45:
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
