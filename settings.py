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
TILE_SIZE   = 64        # logical tile unit (used for physics / movement)
GRID_COLS   = 10        # number of tile columns
GRID_ROWS   = 6         # number of tile rows

# ── Isometric projection ──────────────────────────────────────────────────────
ISO_TILE_W     = 128    # screen width of one tile (2:1 ratio, so height = 64)
ISO_TILE_H     = 64     # screen height of one tile's top-face diamond
ISO_TILE_DEPTH = 32     # visible side-face height (3-D box depth, px)

# Grid screen origin — isometric north vertex of tile (0, 0), centred on screen.
# Centre the TOP FACE (playable surface) on screen; depth extends below.
#   w = (GRID_COLS + GRID_ROWS) * ISO_TILE_W // 2  = 1024 px
#   top_h = (GRID_COLS + GRID_ROWS) * ISO_TILE_H // 2  = 512 px  (top face only)
_ISO_GRID_W     = (GRID_COLS + GRID_ROWS) * ISO_TILE_W // 2         # 1024
_ISO_GRID_TOP_H = (GRID_COLS + GRID_ROWS) * ISO_TILE_H // 2         #  512
ISO_GRID_OFFSET_X = (WINDOW_SIZE[0] - _ISO_GRID_W) // 2 + GRID_ROWS * ISO_TILE_W // 2  # 512
ISO_GRID_OFFSET_Y = (WINDOW_SIZE[1] - _ISO_GRID_TOP_H) // 2                             # 104

# Tile colours
TILE_TOP_COLOR     = ( 93, 187,  69)   # #5DBB45 – top face
TILE_LEFT_COLOR    = ( 61, 140,  47)   # #3D8C2F – left face
TILE_RIGHT_COLOR   = ( 42,  97,  33)   # #2A6121 – right face
TILE_BORDER_COLOR  = ( 25,  55,  20)   # dark border (1 px)
TILE_COLOR_WARNING = (220, 150,  25)   # amber  – about to fall
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
