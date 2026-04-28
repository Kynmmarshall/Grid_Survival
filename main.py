import math
import sys

import pygame

from backend.account_service import AccountService
from audio import get_audio
from game import GameManager
from lan_prompts import draw_lan_backdrop
from online_play.session_flow import run_online_session_setup, wait_for_online_match_start
from scenes import (
    AccountPortalScreen,
    LevelSelectionScreen,
    ModeSelectionScreen,
    PlayerCountSelectionScreen,
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


def _resolve_account_rating(account_service: AccountService, username: str | None) -> int:
    if not username:
        return 1000
    try:
        profile = account_service.get_profile(username)
    except Exception:
        return 1000
    if profile is None:
        return 1000
    try:
        return max(0, int(profile.rr))
    except Exception:
        return 1000


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
            selected_player_count = 2
            network_player_names = None
            ranked_override = None

            if game_mode == MODE_CAMPAIGN:
                ranked_override = _prompt_campaign_ranked_choice(screen, clock)
                if ranked_override is None:
                    continue

            if game_mode == MODE_ONLINE_MULTIPLAYER:
                def _choose_player_count():
                    player_count_screen = PlayerCountSelectionScreen(screen, clock)
                    selected = player_count_screen.run()
                    if selected is None and getattr(player_count_screen, "quit_requested", False):
                        pygame.quit()
                        sys.exit()
                    return selected

                def _choose_level():
                    level_screen = LevelSelectionScreen(screen, clock, game_mode)
                    selected = level_screen.run()
                    if selected is None and getattr(level_screen, "quit_requested", False):
                        pygame.quit()
                        sys.exit()
                    return selected

                def _choose_target_score():
                    target_score_screen = TargetScoreSelectionScreen(screen, clock)
                    selected = target_score_screen.run()
                    if selected is None and getattr(target_score_screen, "quit_requested", False):
                        pygame.quit()
                        sys.exit()
                    return selected

                def _choose_characters(count: int):
                    char_select = PlayerSelectionScreen(
                        screen,
                        clock,
                        game_mode,
                        num_players=max(1, int(count)),
                    )
                    selected = char_select.run()
                    if not selected and getattr(char_select, "quit_requested", False):
                        pygame.quit()
                        sys.exit()
                    return selected

                online_selection = run_online_session_setup(
                    screen,
                    clock,
                    player_name=player_name,
                    rating=_resolve_account_rating(account_service, active_account_username),
                    choose_player_count=_choose_player_count,
                    choose_level=_choose_level,
                    choose_target_score=_choose_target_score,
                    choose_characters=_choose_characters,
                    resolve_level_option=resolve_level_option,
                )
                if online_selection is None:
                    continue

                network = online_selection.network
                local_player_index = int(online_selection.local_player_index)
                selected_level = online_selection.selected_level
                selected_target_score = int(online_selection.selected_target_score)
                selected_player_count = int(online_selection.selected_player_count)
                network_player_names = online_selection.network_player_names
                preselected_online_characters = online_selection.selected_characters
                requires_match_start = bool(online_selection.requires_match_start)
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

            if game_mode != MODE_ONLINE_MULTIPLAYER:
                preselected_online_characters = None
                requires_match_start = False

            while True:
                if preselected_online_characters:
                    selected_characters = list(preselected_online_characters)
                    preselected_online_characters = None
                else:
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

                if game_mode == MODE_ONLINE_MULTIPLAYER and requires_match_start:
                    match_setup = wait_for_online_match_start(
                        screen,
                        clock,
                        network,
                        player_name,
                        selected_characters[0],
                        selected_level.level_id,
                        selected_target_score,
                        selected_player_count,
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
                    selected_player_count = max(
                        2,
                        min(4, int(match_setup.get("player_count", selected_player_count))),
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
