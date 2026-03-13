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
}

WALKABLE_LAYER_NAMES = ["Top"]  # tile layers whose cells are considered walkable
WALKABLE_OBJECT_CLASS_NAMES = ["Platform"]  # Tiled object classes (rect/polygon) that define walkable regions
WALKABLE_ISO_TOP_FRACTION = 1 # for isometric tiles, percentage of height treated as walkable (0-1)

DEBUG_DRAW_WALKABLE = True
DEBUG_WALKABLE_COLOR = (30, 144, 255)
