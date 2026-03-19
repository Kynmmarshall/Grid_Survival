from pathlib import Path
import pygame

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "Assets"

MAP_PATH = ASSETS_DIR / "maps" / "level_1.tmx"
BACKGROUND_PATH = ASSETS_DIR / "Background" / "background.jpg"

CHARACTER_BASE = ASSETS_DIR / "Characters" / "Caveman"

WINDOW_SIZE = (1280, 720)
WINDOW_TITLE = "GRID SURVIVAL"
BACKGROUND_COLOR = (18, 18, 22)
TARGET_FPS = 60

# Map scaling behavior (auto_fit keeps legacy behavior; manual lets you zoom tiles)
MAP_SCALE_MODE = "manual"  # options: "auto_fit", "manual"
MAP_MANUAL_SCALE = 1        # used when MAP_SCALE_MODE == "manual"; >1 enlarges tiles

PLAYER_FRAME_DURATION = 1 / 24
PLAYER_SCALE = 0.2
PLAYER_START_POS = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2)
PLAYER_SPEED = 200
PLAYER_DEFAULT_DIRECTION = "down"
PLAYER_FALL_GRAVITY = 800
PLAYER_FALL_MAX_SPEED = 1000
PLAYER_SINK_SPEED = 80

# Jump mechanics
PLAYER_JUMP_VELOCITY = -400  # Initial upward velocity
PLAYER_JUMP_GRAVITY = 1200  # Gravity during jump
PLAYER_MAX_FALL_SPEED = 600  # Terminal velocity during jump
PLAYER_JUMP_KEY = pygame.K_SPACE  # Default jump key

# Player health
PLAYER_MAX_HEALTH = 3  # Number of hits before elimination (falling still kills instantly)

# ─────────────────────────────────────────────────────────────────────────────
# Level System - Progressive difficulty
# ─────────────────────────────────────────────────────────────────────────────

LEVEL_CONFIG = {
    1: {
        "name": "Training Grounds",
        "disappear_interval": 3.5,  # seconds between tile disappearances
        "min_interval": 1.2,  # fastest tiles disappear
        "simultaneous_tiles": 1,  # how many tiles disappear at once
        "grace_period": 5.0,  # seconds before first tile disappears
        "hazard_frequency": 0.3,  # 0-1, how often hazards spawn
        "tile_density": 0.9,  # 0-1, how many tiles on the map
    },
    2: {
        "name": "The Floating Islands",
        "disappear_interval": 3.0,
        "min_interval": 1.0,
        "simultaneous_tiles": 1,
        "grace_period": 4.0,
        "hazard_frequency": 0.4,
        "tile_density": 0.85,
    },
    3: {
        "name": "Crumbling Bridges",
        "disappear_interval": 2.5,
        "min_interval": 0.9,
        "simultaneous_tiles": 2,
        "grace_period": 3.5,
        "hazard_frequency": 0.5,
        "tile_density": 0.8,
    },
    4: {
        "name": "Shattered Platform",
        "disappear_interval": 2.0,
        "min_interval": 0.75,
        "simultaneous_tiles": 2,
        "grace_period": 3.0,
        "hazard_frequency": 0.6,
        "tile_density": 0.75,
    },
    5: {
        "name": "The Last Stand",
        "disappear_interval": 1.5,
        "min_interval": 0.6,
        "simultaneous_tiles": 3,
        "grace_period": 2.5,
        "hazard_frequency": 0.7,
        "tile_density": 0.7,
    },
    6: {
        "name": "Chaos Realm",
        "disappear_interval": 1.2,
        "min_interval": 0.5,
        "simultaneous_tiles": 3,
        "grace_period": 2.0,
        "hazard_frequency": 0.8,
        "tile_density": 0.65,
    },
    7: {
        "name": "Nightmare",
        "disappear_interval": 1.0,
        "min_interval": 0.4,
        "simultaneous_tiles": 4,
        "grace_period": 1.5,
        "hazard_frequency": 0.9,
        "tile_density": 0.6,
    },
}

MAX_LEVEL = len(LEVEL_CONFIG)
LEVEL_UP_TIME = 30  # seconds of survival to level up
LEVEL_UP_SCORE = 500  # score threshold to level up

# Arena visual - elevated platform
ARENA_PLATFORM_COLOR = (60, 50, 70)
ARENA_PLATFORM_BORDER = (100, 90, 120)
ARENA_WATER_COLOR = (20, 40, 80)
ARENA_WATER_WAVE_HEIGHT = 15

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

# Opening scene audio
MUSIC_PATH = BASE_DIR / "Soundtrack" / "TileSuv2.mp3"
MUSIC_VOLUME = 0.45

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY 1 — TILE DISAPPEARANCE SYSTEM
# ─────────────────────────────────────────────────────────────────────────────

# Tile crumble animation duration (ms → seconds)
TILE_CRUMBLE_DURATION = 0.350  # 350ms

# Grace period before first tile disappears (seconds)
TILE_GRACE_PERIOD = 3.0

# ─────────────────────────────────────────────────────────────────────────────
# SOUND FILE PATHS  (all relative names resolved under Assets/Audio/sfx/)
# ─────────────────────────────────────────────────────────────────────────────

_SFX = ASSETS_DIR / "Audio" / "sfx_generated"

# — Tiles —
SOUND_TILE_WARNING      = str(_SFX / "tile_warning.wav")
SOUND_TILE_CRUMBLE      = str(_SFX / "tile_crumble.wav")
SOUND_TILE_DISAPPEAR    = str(_SFX / "tile_disappear.wav")
SOUND_TILE_GRACE_END    = str(_SFX / "tile_grace_end.wav")

# — Player movement —
SOUND_FOOTSTEP_STONE    = [str(_SFX / "footstep_stone_1.wav"),
                            str(_SFX / "footstep_stone_2.wav")]
SOUND_FOOTSTEP_SOFT     = [str(_SFX / "footstep_soft_1.wav"),
                            str(_SFX / "footstep_soft_2.wav")]
SOUND_JUMP              = str(_SFX / "jump.wav")
SOUND_LAND              = str(_SFX / "land.wav")
SOUND_PLAYER_FALL       = str(_SFX / "player_fall.wav")
SOUND_PLAYER_DROWN      = str(_SFX / "player_drown.wav")
SOUND_SPLASH            = str(_SFX / "splash.wav")
SOUND_PLAYER_ELIMINATED = str(_SFX / "player_eliminated.wav")
SOUND_PLAYER_VICTORY    = str(_SFX / "player_victory.wav")

# — Hazards —
SOUND_BULLET_FIRE       = str(_SFX / "bullet_fire.wav")
SOUND_BULLET_HIT        = str(_SFX / "bullet_hit.wav")
SOUND_TRAP_SPAWN        = str(_SFX / "trap_spawn.wav")
SOUND_TRAP_PATROL       = str(_SFX / "trap_patrol.wav")

# — Powers (activation) —
SOUND_POWER_CAVEMAN     = str(_SFX / "power_caveman_smash.wav")
SOUND_POWER_NINJA_DASH  = str(_SFX / "power_ninja_dash.wav")
SOUND_POWER_NINJA_END   = str(_SFX / "power_ninja_reappear.wav")
SOUND_POWER_WIZARD      = str(_SFX / "power_wizard_freeze.wav")
SOUND_POWER_WIZARD_END  = str(_SFX / "power_wizard_unfreeze.wav")
SOUND_POWER_KNIGHT      = str(_SFX / "power_knight_shield.wav")
SOUND_POWER_KNIGHT_BASH = str(_SFX / "power_knight_bash.wav")
SOUND_POWER_ROBOT       = str(_SFX / "power_robot_overclock.wav")
SOUND_POWER_ROBOT_HIT   = str(_SFX / "power_robot_armour_break.wav")
SOUND_POWER_SAMURAI     = str(_SFX / "power_samurai_bladestorm.wav")
SOUND_POWER_ARCHER      = str(_SFX / "power_archer_volley.wav")
SOUND_POWER_ARROW_HIT   = str(_SFX / "power_arrow_hit.wav")
SOUND_POWER_READY       = str(_SFX / "power_ready.wav")
SOUND_POWER_UNAVAILABLE = str(_SFX / "power_unavailable.wav")

# — UI —
SOUND_UI_SELECT         = str(_SFX / "ui_select.wav")
SOUND_UI_CONFIRM        = str(_SFX / "ui_confirm.wav")
SOUND_UI_BACK           = str(_SFX / "ui_back.wav")
SOUND_COUNTDOWN_BEEP    = str(_SFX / "countdown_beep.wav")
SOUND_COUNTDOWN_GO      = str(_SFX / "countdown_go.wav")

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
HUD_PANEL_BG = (20, 20, 20, 180)
HUD_PANEL_RADIUS = 12
HUD_PANEL_BORDER_WIDTH = 2
HUD_PANEL_PADDING_H = 12
HUD_PANEL_PADDING_V = 8

HUD_SCORE_BORDER_COLOR = (255, 200, 0)       # GOLD
HUD_TIMER_BORDER_COLOR = (220, 220, 220)     # WHITE
HUD_ALIVE_BORDER_COLOR_ALL = (50, 220, 80)   # LIME GREEN
HUD_ALIVE_BORDER_COLOR_ONE = (255, 160, 0)   # ORANGE
HUD_ALIVE_BORDER_COLOR_LAST = (220, 50, 50)  # RED

HUD_TIMER_URGENT_COLOR = (220, 40, 40)       # RED when urgent
HUD_VALUE_COLOR = (255, 255, 255)            # WHITE
HUD_LABEL_COLOR_SCORE = (255, 200, 0)
HUD_LABEL_COLOR_TIMER = (220, 220, 220)
HUD_LABEL_COLOR_ALIVE = (50, 220, 80)

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
MODE_CARD_WIDTH = 460
MODE_CARD_HEIGHT = 145
MODE_CARD_SPACING = 34 + 145  # gap + card height

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
TITLE_SUBTITLE_COLOR = (220, 230, 250)
INPUT_LABEL_COLOR = (160, 160, 160)
INPUT_BOX_BG_COLOR = (30, 30, 30)
INPUT_BOX_BORDER_COLOR = (245, 185, 70)
INPUT_BOX_BORDER_UNFOCUSED = (100, 100, 100)
INPUT_TEXT_COLOR = (255, 255, 255)
PROMPT_TEXT_COLOR = (255, 220, 90)
WARNING_TEXT_COLOR = (220, 60, 60)

MODE_BG_COLOR = (10, 14, 26)
MODE_HEADER_COLOR = (255, 255, 255)
MODE_HEADER_NAME_COLOR = (255, 200, 0)   # GOLD for player name
MODE_SUBTITLE_COLOR = (200, 200, 200)
MODE_CARD_BASE_COLOR = (25, 25, 40, 200)
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