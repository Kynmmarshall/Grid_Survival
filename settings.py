from pathlib import Path

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "Assets"

MAP_PATH = ASSETS_DIR / "maps" / "level_1.tmx"
BACKGROUND_PATH = ASSETS_DIR / "Background" / "background.jpg"

CHARACTER_BASE = ASSETS_DIR / "Characters" / "Caveman"

WINDOW_SIZE = (1280, 720)
WINDOW_TITLE = "GRID SURVIVAL"
BACKGROUND_COLOR = (18, 18, 22)
TARGET_FPS = 60

PLAYER_FRAME_DURATION = 1 / 24  # seconds per frame
PLAYER_SCALE = .2  # set to tuple like (48, 64) if you prefer explicit sizing
PLAYER_START_POS = (WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2)
PLAYER_SPEED = 200  # pixels per second
PLAYER_DEFAULT_DIRECTION = "down"
PLAYER_FALL_GRAVITY = 800  # pixels per second squared
PLAYER_FALL_MAX_SPEED = 1000  # pixels per second
PLAYER_SINK_SPEED = 80 # pixels per second while drowning


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

WALKABLE_LAYER_NAMES = ["Top"]  # tile layers whose cells are considered walkable
WALKABLE_OBJECT_CLASS_NAMES = ["Platform"]  # Tiled object classes (rect/polygon) that define walkable regions
WALKABLE_ISO_TOP_FRACTION = 1  # for isometric tiles, percentage of height treated as walkable (0-1)

DEBUG_VISUALS_ENABLED = False
DEBUG_DRAW_WALKABLE = True
DEBUG_WALKABLE_COLOR = (30, 144, 255)
DEBUG_DRAW_PLAYER_FOOTBOX = True
DEBUG_PLAYER_FOOTBOX_COLOR = (255, 230, 0)

WATER_SPRITESHEET = ASSETS_DIR / "Background" / "Water" / "Animated Water.png"
WATER_FRAME_SIZE = (192, 96)
WATER_FRAME_COUNT = 24
WATER_FRAME_DURATION = 1 / 12
WATER_TARGET_HEIGHT = 150
WATER_SPLASH_SPRITESHEET = ASSETS_DIR / "Background" / "Water" / "Animated Water-Splash-Sheet-192x1344.png"
WATER_SPLASH_FRAME_SIZE = (192, 192)
WATER_SPLASH_FRAME_COUNT = 7
WATER_SPLASH_FRAME_DURATION = 1 / 18
WATER_SPLASH_SIZE = (256, 256)
