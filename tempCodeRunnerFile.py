
import pygame

from audio import get_audio
from game import GameManager
from host_waiting_screen import host_waiting_screen
from lan_prompts import draw_lan_backdrop, prompt_host_or_join, prompt_ip_entry, toast_message
from network import NetworkClient, NetworkHost, get_local_ip
from scenes import (
    LevelSelectionScreen,
    ModeSelectionScreen,
    PlayerSelectionScreen,
    TargetScoreSelectionScreen,
    TitleScreen,
)
from scenes.common import SceneAudioOverlay, _draw_rounded_rect, _load_font
from scenes.level_selection import resolve_level_option
from settings import (
    FONT_PATH_BODY,
    FONT_PATH_HEADING,
    MODE_LOCAL_MULTIPLAYER,