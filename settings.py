import sys
import os
import shutil
from pathlib import Path
import pygame

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "Assets"

MAP_PATH = ASSETS_DIR / "maps" / "level_1.tmx"
BACKGROUND_PATH = ASSETS_DIR / "Background" / "sky1.png"

CHARACTER_BASE = ASSETS_DIR / "Characters" / "Caveman"
PLAYER_PORTRAIT_DIR = ASSETS_DIR / "Characters" / "portrait"

def _detect_display_size() -> tuple[int, int]:
    fallback_size = (1280, 720)

    if sys.platform.startswith("win"):
        try:
            import ctypes

            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except (AttributeError, OSError):
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except AttributeError:
                    pass

            user32 = ctypes.windll.user32
            width = int(user32.GetSystemMetrics(0))
            height = int(user32.GetSystemMetrics(1))
            if width > 0 and height > 0:
                return (width, height)
        except Exception:
            pass

    return fallback_size


WINDOW_SIZE = _detect_display_size()
WINDOW_FLAGS = pygame.NOFRAME  # borderless windowed mode for easier screen capture
WINDOW_TITLE = "GRID SURVIVAL"

# Define Color Palette
COLOR_PALETTE = {
    "background": (18, 18, 22),
    "hud_bg": (20, 20, 20, 180),
    "hud_border": (220, 220, 220),       # White/Grey
    "hud_border_score": (255, 200, 0),   # Gold
    "text_primary": (255, 255, 255),
    "text_secondary": (200, 200, 200),
    "accent": (255, 200, 0),             # Gold
    "urgent": (220, 40, 40),             # Red
    "success": (50, 220, 80),            # Lime Green
    "warning": (255, 160, 0),            # Orange
    "danger": (220, 50, 50),             # Red
}

BACKGROUND_COLOR = COLOR_PALETTE["background"]
TARGET_FPS = 60

# Map scaling behavior (auto_fit keeps legacy behavior; manual lets you zoom tiles)
MAP_SCALE_MODE = "manual"  # options: "auto_fit", "manual"
MAP_MANUAL_SCALE = 1        # used when MAP_SCALE_MODE == "manual"; >1 enlarges tiles

PLAYER_FRAME_DURATION = 1 / 24
PLAYER_SCALE = 0.2
PLAYER_START_POS = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2)
PLAYER_SPEED = 200
PLAYER_DEFAULT_DIRECTION = "down"
PLAYER_FALL_GRAVITY = 1200         # Increased from 800
PLAYER_FALL_MAX_SPEED = 1000
PLAYER_SINK_SPEED = 80

# Jump mechanics
PLAYER_JUMP_VELOCITY = 650         # Initial upward Z velocity (Positive = UP)
PLAYER_JUMP_GRAVITY = 2000         # Gravity acceleration on Z axis
PLAYER_MAX_FALL_SPEED = 1000       # Max fall speed for Z axis
PLAYER_JUMP_KEY = pygame.K_SPACE   # Default jump key

DEFAULT_CONTROLS = {
    "player1": {
        "up": pygame.K_w,
        "down": pygame.K_s,
        "left": pygame.K_a,
        "right": pygame.K_d,
        "jump": pygame.K_SPACE,
        "power": pygame.K_q,
    },
    "player2": {
        "up": pygame.K_UP,
        "down": pygame.K_DOWN,
        "left": pygame.K_LEFT,
        "right": pygame.K_RIGHT,
        "jump": pygame.K_RSHIFT,
        "power": pygame.K_SLASH,
    },
}

def _resolve_controls_file() -> Path:
    """Return the controls file path.

    Source runs keep using the repo file.
    Frozen one-file builds use a persistent user directory so controls survive restarts.
    """
    if getattr(sys, "frozen", False):
        appdata = os.getenv("APPDATA") or os.getenv("LOCALAPPDATA")
        if appdata:
            return Path(appdata) / "Grid_Survival" / "custom_controls.json"
        return Path.home() / ".grid_survival" / "custom_controls.json"
    return BASE_DIR / "custom_controls.json"


CUSTOM_CONTROLS_FILE = _resolve_controls_file()
_LEGACY_CUSTOM_CONTROLS_FILE = BASE_DIR / "custom_controls.json"


def _migrate_legacy_controls_if_needed() -> None:
    """Copy a legacy controls file into the persistent location once."""
    if CUSTOM_CONTROLS_FILE.exists() or not getattr(sys, "frozen", False):
        return

    candidates = [
        Path(sys.executable).resolve().parent / "custom_controls.json",
        Path.cwd() / "custom_controls.json",
        _LEGACY_CUSTOM_CONTROLS_FILE,
    ]

    for source in candidates:
        try:
            if not source.exists():
                continue
            if source.resolve() == CUSTOM_CONTROLS_FILE.resolve():
                continue
            CUSTOM_CONTROLS_FILE.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, CUSTOM_CONTROLS_FILE)
            return
        except Exception:
            continue

_KEY_TO_NAME = {
    pygame.K_SPACE: "SPACE",
    pygame.K_RETURN: "RETURN",
    pygame.K_BACKSPACE: "BACKSPACE",
    pygame.K_TAB: "TAB",
    pygame.K_ESCAPE: "ESCAPE",
    pygame.K_UP: "UP",
    pygame.K_DOWN: "DOWN",
    pygame.K_LEFT: "LEFT",
    pygame.K_RIGHT: "RIGHT",
    pygame.K_LSHIFT: "LSHIFT",
    pygame.K_RSHIFT: "RSHIFT",
    pygame.K_LCTRL: "LCTRL",
    pygame.K_RCTRL: "RCTRL",
    pygame.K_LALT: "LALT",
    pygame.K_RALT: "RALT",
    pygame.K_CAPSLOCK: "CAPSLOCK",
    pygame.K_F1: "F1",
    pygame.K_F2: "F2",
    pygame.K_F3: "F3",
    pygame.K_F4: "F4",
    pygame.K_F5: "F5",
    pygame.K_F6: "F6",
    pygame.K_F7: "F7",
    pygame.K_F8: "F8",
    pygame.K_F9: "F9",
    pygame.K_F10: "F10",
    pygame.K_F11: "F11",
    pygame.K_F12: "F12",
    pygame.K_SCROLLOCK: "SCROLLOCK",
    pygame.K_SYSREQ: "SYSREQ",
    pygame.K_PRINTSCREEN: "PRINTSCREEN",
    pygame.K_PAGEUP: "PAGEUP",
    pygame.K_PAGEDOWN: "PAGEDOWN",
    pygame.K_HOME: "HOME",
    pygame.K_END: "END",
    pygame.K_INSERT: "INSERT",
    pygame.K_DELETE: "DELETE",
    pygame.K_NUMLOCK: "NUMLOCK",
    pygame.K_KP_0: "KP_0",
    pygame.K_KP_1: "KP_1",
    pygame.K_KP_2: "KP_2",
    pygame.K_KP_3: "KP_3",
    pygame.K_KP_4: "KP_4",
    pygame.K_KP_5: "KP_5",
    pygame.K_KP_6: "KP_6",
    pygame.K_KP_7: "KP_7",
    pygame.K_KP_8: "KP_8",
    pygame.K_KP_9: "KP_9",
    pygame.K_KP_PERIOD: "KP_PERIOD",
    pygame.K_KP_DIVIDE: "KP_DIVIDE",
    pygame.K_KP_MULTIPLY: "KP_MULTIPLY",
    pygame.K_KP_MINUS: "KP_MINUS",
    pygame.K_KP_PLUS: "KP_PLUS",
    pygame.K_KP_ENTER: "KP_ENTER",
    pygame.K_SLASH: "SLASH",
    pygame.K_BACKSLASH: "BACKSLASH",
    pygame.K_PERIOD: "PERIOD",
    pygame.K_COMMA: "COMMA",
    pygame.K_SEMICOLON: "SEMICOLON",
    pygame.K_QUOTE: "QUOTE",
    pygame.K_BACKQUOTE: "BACKQUOTE",
    pygame.K_LEFTBRACKET: "LEFTBRACKET",
    pygame.K_RIGHTBRACKET: "RIGHTBRACKET",
    pygame.K_MINUS: "MINUS",
    pygame.K_EQUALS: "EQUALS",
}

_NAME_TO_KEY = {v: k for k, v in _KEY_TO_NAME.items()}


def _default_controls():
    return {
        "player1": {
            "up": "K_w",
            "down": "K_s",
            "left": "K_a",
            "right": "K_d",
            "jump": "K_SPACE",
            "power": "K_q",
        },
        "player2": {
            "up": "K_UP",
            "down": "K_DOWN",
            "left": "K_LEFT",
            "right": "K_RIGHT",
            "jump": "K_RSHIFT",
            "power": "K_SLASH",
        },
    }


def load_custom_controls():
    import json

    _migrate_legacy_controls_if_needed()

    if not CUSTOM_CONTROLS_FILE.exists():
        return None
    try:
        with open(CUSTOM_CONTROLS_FILE, "r") as f:
            data = json.load(f)
        converted = {}
        for player_key, controls in data.items():
            converted_controls = {}
            for action, key_name in controls.items():
                if key_name.startswith("K_"):
                    key_str = key_name[2:]
                    if key_str in _NAME_TO_KEY:
                        converted_controls[action] = _NAME_TO_KEY[key_str]
                    else:
                        converted_controls[action] = getattr(pygame, f"K_{key_str.lower()}", pygame.K_UNKNOWN)
                else:
                    converted_controls[action] = getattr(pygame, key_name, pygame.K_UNKNOWN)
            converted[player_key] = converted_controls
        return converted
    except Exception:
        return None


def save_custom_controls(controls):
    import json

    try:
        CUSTOM_CONTROLS_FILE.parent.mkdir(parents=True, exist_ok=True)
        serializable = {}
        for player_key, player_controls in controls.items():
            serializable_controls = {}
            for action, key_code in player_controls.items():
                key_name = _KEY_TO_NAME.get(key_code)
                if key_name:
                    serializable_controls[action] = f"K_{key_name}"
                else:
                    regular_name = pygame.key.name(key_code)
                    if regular_name and regular_name != "":
                        serializable_controls[action] = f"K_{regular_name.upper()}"
                    else:
                        serializable_controls[action] = f"K_UNKNOWN"
            serializable[player_key] = serializable_controls
        with open(CUSTOM_CONTROLS_FILE, "w") as f:
            json.dump(serializable, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving controls: {e}")
        return False

PLAYER_ANIMATION_PATHS = {
	"idle": {
		"down": CHARACTER_BASE / "idle" / "Front - Idle Blinking",
		"up": CHARACTER_BASE / "idle" / "Back - Idle",
		"left": CHARACTER_BASE / "idle" / "Left - Idle Blinking",
		"right": CHARACTER_BASE / "idle" / "Right - Idle Blinking",
	},
	"run": {
		"down": CHARACTER_BASE / "running" / "Front - Running",
		"up": CHARACTER_BASE / "running" / "Back - Running",
		"left": CHARACTER_BASE / "running" / "Left - Running",
		"right": CHARACTER_BASE / "running" / "Right - Running",
	},
	"death": {
		"down": CHARACTER_BASE / "Dying",
		"up": CHARACTER_BASE / "Dying",
		"left": CHARACTER_BASE / "Dying",
		"right": CHARACTER_BASE / "Dying",
	},
}

WALKABLE_LAYER_NAMES = ["Top"]
WALKABLE_OBJECT_CLASS_NAMES = ["Platform"]
WALKABLE_ISO_TOP_FRACTION = 1
DESTRUCTIBLE_LAYER_NAMES = ["Top"]

DEBUG_VISUALS_ENABLED = False
DEBUG_DRAW_WALKABLE = True
DEBUG_WALKABLE_COLOR = (30, 144, 255)
DEBUG_DRAW_PLAYER_FOOTBOX = True
DEBUG_PLAYER_FOOTBOX_COLOR = (255, 230, 0)
DEBUG_DRAW_PLAYER_COLLISION = True
DEBUG_PLAYER_COLLISION_COLOR = (0, 255, 255)

WATER_SPRITESHEET = ASSETS_DIR / "Background" / "Water" / "Animated Water.png"
WATER_FRAME_SIZE = (192, 96)
WATER_FRAME_COUNT = 24
WATER_FRAME_DURATION = 1 / 12
WATER_TARGET_HEIGHT = 0
WATER_SPLASH_SPRITESHEET = (
	ASSETS_DIR / "Background" / "Water" / "Animated Water-Splash-Sheet-192x1344.png"
)
WATER_SPLASH_FRAME_SIZE = (192, 192)
WATER_SPLASH_FRAME_COUNT = 7
WATER_SPLASH_FRAME_DURATION = 1 / 18
WATER_SPLASH_SIZE = (256, 256)

# Terrain animation themes let you swap the edge effect (water, lava, void, etc.)
# without touching code. Set ACTIVE_TERRAIN_THEME to pick which entry should run
# and edit/duplicate the dictionaries below to point at the correct art.
ACTIVE_TERRAIN_THEME = "space"  # options: "space", "water", add more as needed
TERRAIN_THEMES = {
	"space": {
		"base": None,   # No base animation for outer space
		"splash": None, # No splash effect
	},
	"water": {
		"base": {
			"spritesheet": WATER_SPRITESHEET,
			"frame_size": WATER_FRAME_SIZE,
			"frame_count": WATER_FRAME_COUNT,
			"frame_duration": WATER_FRAME_DURATION,
			"target_height": WATER_TARGET_HEIGHT,
		},
		"splash": {
			"spritesheet": WATER_SPLASH_SPRITESHEET,
			"frame_size": WATER_SPLASH_FRAME_SIZE,
			"frame_count": WATER_SPLASH_FRAME_COUNT,
			"frame_duration": WATER_SPLASH_FRAME_DURATION,
			"size": WATER_SPLASH_SIZE,
		},
	},
	"lava": {
		# Example placeholder — point these at your lava assets when ready.
		"base": None,
		"splash": None,
	},
}

USE_AI_PLAYER = True
AI_DECISION_INTERVAL = 0.22
AI_LOOKAHEAD_DISTANCE = 42
AI_EDGE_MARGIN_WEIGHT = 0.06
AI_DEFAULT_DIFFICULTY = 5
ORB_LIFETIME = 20.0
ORB_SHIELD_DURATION = 20.0
ORB_SHIELD_WARNING = 4.0
ORB_FREEZE_DURATION = 5.0
ORB_VOID_WALK_DURATION = 10.0
POWER_ORBS_REQUIRED = 1
ORB_ICON_PATHS = {
	"speed": str(ASSETS_DIR / "orbs" / "speed.png"),
	"shield": str(ASSETS_DIR / "orbs" / "shield.png"),
	"freeze": str(ASSETS_DIR / "orbs" / "freeze.png"),
	"power": str(ASSETS_DIR / "orbs" / "power.png"),
	"life": str(ASSETS_DIR / "orbs" / "life.png"),
	"phase": str(ASSETS_DIR / "orbs" / "phase.png"),
}
SHIELD_EFFECT_PATH = ASSETS_DIR / "effects" / "shield.png"
VOID_WALK_WING_PATH = ASSETS_DIR / "effects" / "void_walk_wing.png"

# Opening scene audio
BACKGROUND_MUSIC_TRACKS = [
	ASSETS_DIR / "Audio" / "Background" / "Grid survival 1.mp3",
	ASSETS_DIR / "Audio" / "Background" / "Grid survival 2.mp3",
	ASSETS_DIR / "Audio" / "Background" / "Grid survival 3.mp3",
	ASSETS_DIR / "Audio" / "Background" / "Grid survival 4.mp3",
	ASSETS_DIR / "Audio" / "Background" / "Grid survival 5.mp3",
	ASSETS_DIR / "Audio" / "Background" / "Grid survival 6.mp3",
	ASSETS_DIR / "Audio" / "Background" / "Grid survival 7.mp3",
]
TUTORIAL_VIDEO_PATH = ASSETS_DIR / "tutorial" / "1.mp4"
MUSIC_PATH = BACKGROUND_MUSIC_TRACKS[0]
MUSIC_VOLUME = 0.45
AUDIO_VOLUME_STEP = 0.05

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 1 — TILE DISAPPEARANCE SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

# Tile crumble animation duration (ms → seconds)
TILE_CRUMBLE_DURATION = 0.350  # 350ms

# Grace period before first tile disappears (seconds)
TILE_GRACE_PERIOD = 3.0

# Sound file paths
SOUND_TILE_WARNING = str(ASSETS_DIR / "Audio" / "SFX" / "hit.wav")
SOUND_TILE_CRUMBLE = str(ASSETS_DIR / "Audio" / "sfx_generated" / "tile_crumble.wav")
SOUND_TILE_DISAPPEAR = str(ASSETS_DIR / "Audio" / "SFX" / "destroy.wav")
SOUND_TILE_GRACE_END = str(ASSETS_DIR / "Audio" / "sfx_generated" / "tile_grace_end.wav")
SOUND_PLAYER_FALL = str(ASSETS_DIR / "Audio" / "SFX" / "fall.wav")
SOUND_PLAYER_JUMP = str(ASSETS_DIR / "Audio" / "SFX" / "jump.wav")

# Character power audio cues
POWER_SFX_DIR = ASSETS_DIR / "Audio" / "sfx_generated"
SOUND_POWER_READY = str(POWER_SFX_DIR / "power_ready.wav")
SOUND_POWER_UNAVAILABLE = str(POWER_SFX_DIR / "power_unavailable.wav")
SOUND_POWER_CAVEMAN = str(POWER_SFX_DIR / "power_caveman_smash.wav")
SOUND_POWER_NINJA_DASH = str(POWER_SFX_DIR / "power_ninja_dash.wav")
SOUND_POWER_NINJA_END = str(POWER_SFX_DIR / "power_ninja_reappear.wav")
SOUND_POWER_WIZARD = str(POWER_SFX_DIR / "power_wizard_freeze.wav")
SOUND_POWER_WIZARD_END = str(POWER_SFX_DIR / "power_wizard_unfreeze.wav")
SOUND_SHIELD = str(POWER_SFX_DIR / "shield.wav")
SOUND_POWER_KNIGHT_BASH = str(POWER_SFX_DIR / "power_knight_bash.wav")
SOUND_POWER_ROBOT = str(POWER_SFX_DIR / "power_robot_overclock.wav")
SOUND_POWER_ROBOT_HIT = str(POWER_SFX_DIR / "power_robot_armour_break.wav")
SOUND_POWER_SAMURAI = str(POWER_SFX_DIR / "power_samurai_bladestorm.wav")
SOUND_POWER_ARCHER = str(POWER_SFX_DIR / "power_archer_volley.wav")
SOUND_POWER_ARROW_HIT = str(POWER_SFX_DIR / "power_arrow_hit.wav")

# Player fall animation duration (seconds)
PLAYER_FALL_ANIM_DURATION = 0.5

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 2 — IN-GAME HUD
# ─────────────────────────────────────────────────────────────────────────────

# Font paths
FONT_PATH_HUD = str(ASSETS_DIR / "fonts" / "PressStart2P.ttf")
FONT_SIZE_LABEL = 12
FONT_SIZE_VALUE = 32
FONT_SIZE_LARGE = 48   # for timer when urgent

# Timer urgency threshold (seconds remaining)
TIMER_WARNING_THRESHOLD = 10

# HUD panel colors
HUD_PANEL_BG = COLOR_PALETTE["hud_bg"]
HUD_PANEL_RADIUS = 12
HUD_PANEL_BORDER_WIDTH = 2
HUD_PANEL_PADDING_H = 12
HUD_PANEL_PADDING_V = 8

HUD_SCORE_BORDER_COLOR = COLOR_PALETTE["hud_border_score"]     # GOLD
HUD_TIMER_BORDER_COLOR = COLOR_PALETTE["hud_border"]           # WHITE
HUD_ALIVE_BORDER_COLOR_ALL = COLOR_PALETTE["success"]          # LIME GREEN
HUD_ALIVE_BORDER_COLOR_ONE = COLOR_PALETTE["warning"]          # ORANGE
HUD_ALIVE_BORDER_COLOR_LAST = COLOR_PALETTE["danger"]          # RED

HUD_TIMER_URGENT_COLOR = COLOR_PALETTE["urgent"]     # RED when urgent
HUD_VALUE_COLOR = COLOR_PALETTE["text_primary"]      # WHITE
HUD_LABEL_COLOR_SCORE = COLOR_PALETTE["accent"]
HUD_LABEL_COLOR_TIMER = COLOR_PALETTE["text_secondary"]
HUD_LABEL_COLOR_ALIVE = COLOR_PALETTE["success"]

# Score animation
SCORE_ANIM_SCALE_UP_DURATION = 0.2   # seconds
SCORE_ANIM_SCALE_DOWN_DURATION = 0.15

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 3 — OPENING SCREENS FONT HIERARCHY
# ─────────────────────────────────────────────────────────────────────────────

# Font paths for opening screens
FONT_PATH_DISPLAY = str(ASSETS_DIR / "fonts" / "PressStart2P.ttf")
FONT_PATH_HEADING = str(ASSETS_DIR / "fonts" / "PressStart2P.ttf")
FONT_PATH_BODY = str(ASSETS_DIR / "fonts" / "Orbitron-Regular.ttf")
FONT_PATH_SMALL = str(ASSETS_DIR / "fonts" / "Orbitron-Regular.ttf")

FONT_SIZE_DISPLAY = 64       # Game title (reduced from 150 for PressStart2P readability)
FONT_SIZE_HEADING = 32       # Screen subtitles
FONT_SIZE_BODY = 22          # Button labels
FONT_SIZE_SMALL = 18         # Input labels, hints

# Opening scenes visual constants (legacy kept for compatibility)
TITLE_TEXT = "GRID SURVIVAL"
TITLE_FONT_SIZE = 96
TITLE_SUB_FONT_SIZE = 34
INPUT_FONT_SIZE = 36
WARNING_FONT_SIZE = 28
MODE_HEADER_FONT_SIZE = 64
MODE_SUBTITLE_FONT_SIZE = 34
MODE_CARD_TITLE_SIZE = 36
MODE_CARD_DESC_SIZE = 24

TITLE_PARTICLE_COUNT = 90
TITLE_PARTICLE_MIN_SIZE = 6
TITLE_PARTICLE_MAX_SIZE = 16
TITLE_PARTICLE_MIN_SPEED = 20
TITLE_PARTICLE_MAX_SPEED = 70

NAME_MAX_LENGTH = 16
INPUT_BOX_WIDTH = 320
INPUT_BOX_HEIGHT = 52
MODE_CARD_WIDTH = 440
MODE_CARD_HEIGHT = 115
MODE_CARD_SPACING = 34 + 115  # gap + card height

SCENE_FADE_SPEED = 420  # alpha units per second
TITLE_DROP_DURATION = 0.85
TITLE_PULSE_SPEED = 3.2
PROMPT_BLINK_SPEED = 2.0
MODE_CLICK_FLASH_TIME = 0.15

# Title shake animation
TITLE_SHAKE_INTERVAL = 4.0   # seconds between shakes
TITLE_SHAKE_OFFSET = 3       # pixels
TITLE_SHAKE_FRAMES = 3       # rapid frames

# Subtitle float animation
SUBTITLE_FLOAT_AMPLITUDE = 3  # pixels
SUBTITLE_FLOAT_SPEED = 1.0    # cycles per second

# Cursor blink speed
CURSOR_BLINK_SPEED = 2.0  # blinks per second (0.5s period)

# Warning display duration
WARNING_DISPLAY_DURATION = 2.0  # seconds

# Mode selection header animation
MODE_HEADER_SLIDE_DURATION = 1.5   # seconds
MODE_HEADER_SLIDE_DISTANCE = 80    # pixels
MODE_SUBTITLE_DELAY = 0.15         # seconds after header

TITLE_BG_COLOR = (12, 15, 28)
TITLE_BG_IMAGE_PATH = ASSETS_DIR / "Background" / "title_bg.png"  # New background path

TITLE_SUBTITLE_COLOR = (220, 230, 250)
INPUT_LABEL_COLOR = (160, 160, 160)

INPUT_BOX_BG_COLOR = (30, 30, 30)
INPUT_BOX_BORDER_COLOR = (245, 185, 70)
INPUT_BOX_BORDER_UNFOCUSED = (100, 100, 100)
INPUT_TEXT_COLOR = (255, 255, 255)
PROMPT_TEXT_COLOR = (255, 220, 90)
WARNING_TEXT_COLOR = (220, 60, 60)

MODE_BG_COLOR = (10, 14, 26)
MODE_BG_IMAGE_PATH = ASSETS_DIR / "Background" / "mode_bg.png"  # New mode background path
MODE_HEADER_COLOR = (255, 255, 255)
MODE_HEADER_NAME_COLOR = (255, 200, 0)   # GOLD for player name
MODE_SUBTITLE_COLOR = (200, 200, 200)
MODE_CARD_BASE_COLOR = (25, 25, 40, 200)
MODE_CARD_DISABLED_COLOR = (24, 28, 44, 200)
MODE_CARD_HOVER_COLOR = (40, 40, 70, 230)
MODE_CARD_BORDER_COLOR = (230, 190, 80)
MODE_CARD_TITLE_COLOR = (255, 255, 255)
MODE_CARD_DESC_COLOR = (200, 200, 200)
MODE_CARD_CLICK_BASE = (90, 110, 50)
TITLE_PARTICLE_COLOR_BASE = (255, 180, 60)
SCENE_OVERLAY_COLOR = (0, 0, 0)

# Mode card border colors per mode
MODE_CARD_BORDER_VS_COMPUTER = (0, 200, 255)       # CYAN
MODE_CARD_BORDER_LOCAL_MP = (50, 220, 80)           # GREEN
MODE_CARD_BORDER_ONLINE_MP = (180, 80, 255)         # PURPLE
MODE_CARD_BORDER_CAMPAIGN = (255, 180, 50)          # GOLD
MODE_CARD_HOVER_BORDER_CAMPAIGN = (255, 220, 130)

# Mode card hover border (lightened)
MODE_CARD_HOVER_BORDER_VS_COMPUTER = (80, 220, 255)
MODE_CARD_HOVER_BORDER_LOCAL_MP = (100, 255, 130)
MODE_CARD_HOVER_BORDER_ONLINE_MP = (210, 130, 255)

TITLE_COLORS = [
	(255, 200, 0),    # GOLD
	(255, 140, 40),   # ORANGE
	(255, 70, 70),    # RED
]

MODE_VS_COMPUTER = "vs_computer"
MODE_LOCAL_MULTIPLAYER = "local_multiplayer"
MODE_ONLINE_MULTIPLAYER = "online_multiplayer"
MODE_CAMPAIGN = "campaign"
