from pathlib import Path

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "Assets"

MAP_PATH = ASSETS_DIR / "maps" / "level 1.tmx"
BACKGROUND_PATH = ASSETS_DIR / "Background" / "background.jpg"

# ── Window ────────────────────────────────────────────────────────────────────
WINDOW_SIZE = (1280, 720)
WINDOW_TITLE = "GRID SURVIVAL"
BACKGROUND_COLOR = (18, 18, 22)
TARGET_FPS = 60

# ── Tile & Grid ───────────────────────────────────────────────────────────────
TILE_SIZE   = 64        # pixels per tile (square)
GRID_COLS   = 10        # number of tile columns
GRID_ROWS   = 6         # number of tile rows

# Grid top-left pixel position — centered in the window
GRID_ORIGIN_X = (1280 - GRID_COLS * TILE_SIZE) // 2   # 320
GRID_ORIGIN_Y = (720  - GRID_ROWS * TILE_SIZE) // 2   # 168

# Tile colours (placeholder until pixel-art assets arrive)
TILE_COLOR_NORMAL  = ( 72, 160,  72)   # green  – walkable
TILE_COLOR_WARNING = (220, 150,  25)   # amber  – about to fall
TILE_COLOR_BORDER  = ( 35,  80,  35)   # dark green border
TILE_COLOR_VOID    = ( 12,  12,  18)   # hole   – disappeared tile bg

# Tile state timing
TILE_WARNING_TIME = 2.0   # seconds the tile flashes before disappearing
TILE_FLASH_RATE   = 0.30  # initial seconds per flash toggle (speeds up)

# How many new tiles are scheduled to disappear per second
TILES_PER_SECOND  = 0.4   # 1 tile every 2.5 s at difficulty level 1

# ── Player ────────────────────────────────────────────────────────────────────
PLAYER_SIZE       = 44    # px (smaller than TILE_SIZE so it fits inside)
PLAYER_COLOR      = (220,  70,  70)   # red placeholder
PLAYER_SPEED      = 320   # px per second for smooth tile-to-tile tween
PLAYER_FALL_SPEED = 480   # px per second initial fall speed

