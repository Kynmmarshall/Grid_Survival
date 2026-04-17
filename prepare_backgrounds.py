# This script assumes the user has placed the new background images in the Assets/Background directory
# or provided them in a way that I can reference.
# Since I cannot extract images from the chat, I will modify the settings.py to point to new filenames
# and instructions for the user to save them.

# Step 1: Update settings.py to include paths for the new backgrounds.
# Step 2: Update scenes/title_screen.py to load and draw opacity overlay.
# Step 3: Update scenes/mode_selection.py to load and draw opacity overlay.

import pygame
from settings import ASSETS_DIR

# Define new paths
TITLE_BG_PATH = ASSETS_DIR / "Background" / "title_bg.png"
MODE_BG_PATH = ASSETS_DIR / "Background" / "mode_bg.png"

def load_and_scale_bg(path, window_size):
    if not path.exists():
        return None
    image = pygame.image.load(str(path)).convert()
    
    # Scale to cover (fill)
    img_w, img_h = image.get_size()
    win_w, win_h = window_size
    
    scale_w = win_w / img_w
    scale_h = win_h / img_h
    scale = max(scale_w, scale_h)
    
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    
    scaled = pygame.transform.smoothscale(image, (new_w, new_h))
    
    # Center crop
    x = (new_w - win_w) // 2
    y = (new_h - win_h) // 2
    
    return scaled.subsurface((x, y, win_w, win_h))

# Step 2 & 3 will be done by editing the files.
