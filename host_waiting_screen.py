import math
import sys

import pygame

from lan_prompts import draw_lan_backdrop
from scenes.common import SceneAudioOverlay, _draw_rounded_rect, _load_font
from settings import (
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    WINDOW_SIZE,
)


def _draw_waiting_panel(
    screen,
    title: str,
    lines: list[str],
    *,
    accent=(180, 80, 255),
    success=False,
    audio_overlay: SceneAudioOverlay | None = None,
):
    width, height = WINDOW_SIZE
    font_title = _load_font(FONT_PATH_HEADING, 34, bold=True)
    font_body = _load_font(FONT_PATH_BODY, 24)
    font_small = _load_font(FONT_PATH_BODY, 18)
    anim_time = pygame.time.get_ticks() / 1000.0
    draw_lan_backdrop(screen, anim_time)

    panel = pygame.Rect(0, 0, min(860, width - 120), 280)
    panel.center = (width // 2, height // 2)
    border = (60, 220, 80) if success else accent
    pulse = 0.5 + 0.5 * math.sin(anim_time * 2.8)
    glow = pygame.Surface((panel.width + 20, panel.height + 20), pygame.SRCALPHA)
    pygame.draw.rect(
        glow,
        (border[0], border[1], border[2], int(28 + 20 * pulse)),
        glow.get_rect(),
        border_radius=24,
    )
    screen.blit(glow, (panel.left - 10, panel.top - 10), special_flags=pygame.BLEND_ADD)
    _draw_rounded_rect(screen, panel, (20, 28, 48), border, 3, 18)

    title_surf = font_title.render(title, True, (255, 255, 255))
    screen.blit(title_surf, title_surf.get_rect(center=(panel.centerx, panel.top + 48)))

    y = panel.top + 104
    for idx, line in enumerate(lines):
        font = font_body if idx == 0 else font_small
        color = accent if idx == 0 else (215, 220, 235)
        if success:
            color = (60, 220, 80) if idx == 0 else (215, 220, 235)
        surf = font.render(line, True, color)
        screen.blit(surf, surf.get_rect(center=(panel.centerx, y)))
        y += 40 if idx == 0 else 30

    if audio_overlay is not None:
        audio_overlay.draw(screen)

    pygame.display.flip()


def host_waiting_screen(
    screen,
    clock,
    host_ip: str,
    network,
    public_ip=None,
    upnp_status=None,
):
    """Wait for a LAN or internet client while keeping the host UI responsive.

    Parameters
    ----------
    host_ip:
        The machine's LAN/local IP address.
    network:
        The :class:`~network.NetworkHost` instance.
    public_ip:
        Either a ``str | None`` value **or** a zero-argument callable that
        returns one.  Pass a lambda so the display updates as a background
        thread resolves the public IP.
    upnp_status:
        Either a ``str | None`` value **or** a zero-argument callable.
        Displays the UPnP mapping result (or a manual port-forward hint).
    """
    audio_overlay = SceneAudioOverlay()
    port = getattr(network, "port", 5555)

    while True:
        connected = network.poll_connection()

        # Resolve dynamic values each tick so background-thread results appear
        # on screen as soon as they become available.
        current_pub_ip = public_ip() if callable(public_ip) else public_ip
        current_upnp = upnp_status() if callable(upnp_status) else upnp_status

        # Build info lines based on what we know so far.
        if current_pub_ip:
            pub_line = f"Internet IP: {current_pub_ip}  (port {port})"
            hint_line = "LAN players use the LAN IP  \u2022  Internet players use the Internet IP"
        else:
            pub_line = "Internet IP: checking\u2026  (port {})".format(port)
            hint_line = "Ensure port {} is forwarded on your router for internet play".format(port)

        upnp_line = (
            f"UPnP: {current_upnp}"
            if current_upnp
            else f"Port {port} \u2014 forward this on your router for internet play"
        )

        lines = [
            f"LAN IP: {host_ip}",
            pub_line,
            hint_line,
            upnp_line,
            "Press ESC to cancel.",
        ]

        _draw_waiting_panel(
            screen,
            "Waiting For Player To Join",
            lines,
            accent=(180, 80, 255),
            audio_overlay=audio_overlay,
        )

        if connected:
            peer_ip = network.peer_address[0] if network.peer_address else "Unknown"
            for _ in range(24):
                _draw_waiting_panel(
                    screen,
                    "Player Connected",
                    [peer_ip, "Preparing the match lobby\u2026"],
                    success=True,
                    audio_overlay=audio_overlay,
                )
                clock.tick(30)
            return True

        if network.last_error:
            return False

        for event in pygame.event.get():
            if audio_overlay.handle_event(event):
                continue
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False
        clock.tick(30)
