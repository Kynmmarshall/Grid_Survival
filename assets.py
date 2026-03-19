import math
import pygame

from settings import (
    BACKGROUND_PATH,
    MAP_PATH,
    WALKABLE_LAYER_NAMES,
    WALKABLE_OBJECT_CLASS_NAMES,
    WALKABLE_ISO_TOP_FRACTION,
    DESTRUCTIBLE_LAYER_NAMES,
    MAP_SCALE_MODE,
    MAP_MANUAL_SCALE,
)

try:
    from pytmx.util_pygame import load_pygame
except ImportError:  # pragma: no cover - informs developer about missing dependency
    load_pygame = None


def _calculate_surface_size(tmx_data):
    if tmx_data.orientation == "isometric":
        width = (tmx_data.width + tmx_data.height) * (tmx_data.tilewidth / 2)
        height = (tmx_data.width + tmx_data.height) * (tmx_data.tileheight / 2)
    else:
        width = tmx_data.width * tmx_data.tilewidth
        height = tmx_data.height * tmx_data.tileheight

    return math.ceil(width), math.ceil(height)


def _tile_to_pixel(x, y, layer, tmx_data):
    layer_offset_x = getattr(layer, "offsetx", 0)
    layer_offset_y = getattr(layer, "offsety", 0)
    tile_offset = getattr(tmx_data, "tileoffset", (0, 0)) or (0, 0)
    tile_offset_x, tile_offset_y = tile_offset

    if tmx_data.orientation == "isometric":
        half_width = tmx_data.tilewidth / 2
        half_height = tmx_data.tileheight / 2
        origin_x = tmx_data.height * half_width
        pixel_x = (x - y) * half_width + origin_x
        pixel_y = (x + y) * half_height
    else:
        pixel_x = x * tmx_data.tilewidth
        pixel_y = y * tmx_data.tileheight

    pixel_x += layer_offset_x + tile_offset_x
    pixel_y += layer_offset_y + tile_offset_y
    return int(round(pixel_x)), int(round(pixel_y))


def _render_tmx_to_surface(
    tmx_data,
    *,
    include_layers: list[str] | None = None,
    exclude_layers: list[str] | None = None,
) -> pygame.Surface:
    """Draw filtered TMX layers onto a surface."""

    map_width, map_height = _calculate_surface_size(tmx_data)
    surface = pygame.Surface((map_width, map_height), pygame.SRCALPHA)

    include = {name.lower() for name in include_layers or [] if name}
    exclude = {name.lower() for name in exclude_layers or [] if name}
    use_include = bool(include_layers)

    for layer in tmx_data.visible_layers:
        if not hasattr(layer, "tiles"):
            continue
        layer_name = getattr(layer, "name", "").lower()
        if use_include and layer_name not in include:
            continue
        if exclude and layer_name in exclude:
            continue

        for x, y, image in layer.tiles():
            pos = _tile_to_pixel(x, y, layer, tmx_data)
            surface.blit(image, pos)

    return surface


WALKABLE_FILL_COLOR = (255, 255, 255, 255)


def _draw_iso_top(surface, pos, tilewidth, tileheight):
    fraction = max(0.0, min(1.0, WALKABLE_ISO_TOP_FRACTION))
    if fraction <= 0:
        return

    top_y = pos[1]
    bottom_y = pos[1] + tileheight * fraction
    mid_y = (top_y + bottom_y) / 2
    center_x = pos[0] + tilewidth / 2
    left_x = pos[0]
    right_x = pos[0] + tilewidth

    points = [
        (int(round(center_x)), int(round(top_y))),
        (int(round(right_x)), int(round(mid_y))),
        (int(round(center_x)), int(round(bottom_y))),
        (int(round(left_x)), int(round(mid_y))),
    ]
    pygame.draw.polygon(surface, WALKABLE_FILL_COLOR, points)


def _render_walkable_surface(tmx_data, layer_names, object_class_names):
    map_width, map_height = _calculate_surface_size(tmx_data)
    surface = pygame.Surface((map_width, map_height), pygame.SRCALPHA)
    target_layers = {name.lower() for name in (layer_names or []) if name}
    target_classes = {name.lower() for name in (object_class_names or []) if name}
    is_iso = tmx_data.orientation == "isometric"

    if target_layers:
        for layer in tmx_data.layers:
            if getattr(layer, "name", "").lower() not in target_layers:
                continue
            if not hasattr(layer, "tiles"):
                continue

            for x, y, _ in layer.tiles():
                pos = _tile_to_pixel(x, y, layer, tmx_data)
                if is_iso:
                    _draw_iso_top(surface, pos, tmx_data.tilewidth, tmx_data.tileheight)
                else:
                    rect = pygame.Rect(pos, (tmx_data.tilewidth, tmx_data.tileheight))
                    pygame.draw.rect(surface, WALKABLE_FILL_COLOR, rect)

    if target_classes:
        for layer in tmx_data.layers:
            if not hasattr(layer, "objects"):
                continue
            layer_offset_x = getattr(layer, "offsetx", 0)
            layer_offset_y = getattr(layer, "offsety", 0)

            for obj in layer:
                obj_class = (
                    getattr(obj, "class", None)
                    or getattr(obj, "type", None)
                    or ""
                ).lower()
                if obj_class not in target_classes:
                    continue

                width = getattr(obj, "width", 0)
                height = getattr(obj, "height", 0)
                if width <= 0 or height <= 0:
                    continue

                rect = pygame.Rect(
                    int(round(obj.x + layer_offset_x)),
                    int(round(obj.y + layer_offset_y)),
                    int(round(width)),
                    int(round(height)),
                )

                if is_iso:
                    scaled_height = int(
                        round(height * max(0.0, min(1.0, WALKABLE_ISO_TOP_FRACTION)))
                    )
                    if scaled_height <= 0:
                        continue
                    rect.height = scaled_height
                pygame.draw.rect(surface, WALKABLE_FILL_COLOR, rect)

    return surface


def _determine_scaling(raw_width: int, raw_height: int, window_size) -> tuple[float, float]:
    if raw_width <= 0 or raw_height <= 0:
        return 1.0, 1.0

    mode = (MAP_SCALE_MODE or "").lower()
    if mode == "manual":
        manual_scale = max(0.1, float(MAP_MANUAL_SCALE))
        return manual_scale, manual_scale

    # Legacy behavior: stretch independently to fill the window.
    return (
        window_size[0] / raw_width,
        window_size[1] / raw_height,
    )


def _blit_scaled(surface: pygame.Surface, window_size, scale_x: float, scale_y: float):
    scaled_width = max(1, int(round(surface.get_width() * scale_x)))
    scaled_height = max(1, int(round(surface.get_height() * scale_y)))
    if scaled_width == surface.get_width() and scaled_height == surface.get_height():
        scaled = surface.copy()
    else:
        scaled = pygame.transform.smoothscale(surface, (scaled_width, scaled_height))

    canvas = pygame.Surface(window_size, pygame.SRCALPHA)
    offset_x = (window_size[0] - scaled_width) // 2
    offset_y = (window_size[1] - scaled_height) // 2
    canvas.blit(scaled, (offset_x, offset_y))
    return canvas, (offset_x, offset_y), (scaled_width, scaled_height)


def load_tilemap_surface(window_size):
    """Load the TMX tilemap, scale it, and build the walkable mask."""
    if load_pygame is None:
        print("Install pytmx (pip install pytmx) to render Tiled maps.")
        return None, None, None, None, 1.0, 1.0, (0, 0)

    if not MAP_PATH.exists():
        print(f"Map file not found: {MAP_PATH}")
        return None, None, None, None, 1.0, 1.0, (0, 0)

    tmx_data = load_pygame(MAP_PATH.as_posix())
    destructible_layers = DESTRUCTIBLE_LAYER_NAMES or []
    raw_surface = _render_tmx_to_surface(
        tmx_data,
        exclude_layers=destructible_layers if destructible_layers else None,
    )

    scale_x, scale_y = _determine_scaling(raw_surface.get_width(), raw_surface.get_height(), window_size)
    scaled_surface, offset, scaled_size = _blit_scaled(raw_surface, window_size, scale_x, scale_y)


    walkable_surface_raw = _render_walkable_surface(
        tmx_data, WALKABLE_LAYER_NAMES, WALKABLE_OBJECT_CLASS_NAMES
    )
    if walkable_surface_raw.get_size() != raw_surface.get_size():
        # Ensure raw walkable data matches the TMX render size for consistent scaling.
        walkable_surface_raw = pygame.transform.smoothscale(
            walkable_surface_raw,
            raw_surface.get_size(),
        )
    # Scale walkable surface using the same dimensions to keep masks aligned.
    walkable_scaled = pygame.transform.smoothscale(walkable_surface_raw, scaled_size)
    walkable_canvas = pygame.Surface(window_size, pygame.SRCALPHA)
    walkable_canvas.blit(walkable_scaled, offset)

    walkable_bounds = walkable_canvas.get_bounding_rect()
    if walkable_bounds.width == 0 or walkable_bounds.height == 0:
        walkable_bounds = None
    walkable_mask = (
        pygame.mask.from_surface(walkable_canvas)
        if walkable_canvas.get_width() and walkable_canvas.get_height()
        else None
    )

    return (
        scaled_surface,
        tmx_data,
        walkable_mask,
        walkable_bounds,
        scale_x,
        scale_y,
        offset,
    )


def load_background_surface(window_size):
    """Load and scale the background image if it exists."""
    if not BACKGROUND_PATH.exists():
        print(f"Background image not found: {BACKGROUND_PATH}")
        return None

    image = pygame.image.load(BACKGROUND_PATH.as_posix()).convert()
    return pygame.transform.smoothscale(image, window_size)
