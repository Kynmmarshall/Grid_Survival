import pygame

from settings import BACKGROUND_PATH, MAP_PATH

try:
    from pytmx.util_pygame import load_pygame
except ImportError:  # pragma: no cover - informs developer about missing dependency
    load_pygame = None


def _render_tmx_to_surface(tmx_data) -> pygame.Surface:
    """Draw all visible tiles from the TMX data onto a surface."""
    map_width = tmx_data.width * tmx_data.tilewidth
    map_height = tmx_data.height * tmx_data.tileheight
    surface = pygame.Surface((map_width, map_height), pygame.SRCALPHA)

    for layer in tmx_data.visible_layers:
        if hasattr(layer, "tiles"):
            for x, y, image in layer.tiles():
                surface.blit(image, (x * tmx_data.tilewidth, y * tmx_data.tileheight))

    return surface


def load_tilemap_surface(window_size):
    """Load and scale the TMX tilemap to the requested size.

    Returns a tuple of (scaled_surface, tmx_data) so callers can reuse metadata.
    """
    if load_pygame is None:
        print("Install pytmx (pip install pytmx) to render Tiled maps.")
        return None, None

    if not MAP_PATH.exists():
        print(f"Map file not found: {MAP_PATH}")
        return None, None

    tmx_data = load_pygame(MAP_PATH.as_posix())
    raw_surface = _render_tmx_to_surface(tmx_data)
    scaled_surface = pygame.transform.smoothscale(raw_surface, window_size)
    return scaled_surface, tmx_data


def load_background_surface(window_size):
    """Load and scale the background image if it exists."""
    if not BACKGROUND_PATH.exists():
        print(f"Background image not found: {BACKGROUND_PATH}")
        return None

    image = pygame.image.load(BACKGROUND_PATH.as_posix()).convert()
    return pygame.transform.smoothscale(image, window_size)
