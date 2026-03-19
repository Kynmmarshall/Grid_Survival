from pathlib import Path
import pygame

animation=  "Front - Running" #Left Right Back
INPUT_DIR = Path(f"Assets\\Characters\\Caveman\\running\\{animation}")
INPUT_PATTERN = "Front - Running_{:03d}.png"
OUTPUT_DIR = Path(f"Assets\\Characters\\cropped\\{animation}")
FRAME_COUNT = 12

# Choose exactly one of these to control the resize factor.
SCALE_PERCENTX = 19  # e.g., 75 keeps 75% of original size
SCALE_PERCENTY = 21  # e.g., 75 keeps 75% of original size
SCALE_RATIO = None  # e.g., 0.75 overrides SCALE_PERCENT


def crop_to_sprite(image):
    """Crop image to the bounding box of non-transparent pixels."""
    rect = image.get_bounding_rect()
    cropped = pygame.Surface(rect.size, pygame.SRCALPHA)
    cropped.blit(image, (0, 0), rect)
    return cropped


def resize_sprite(image):
    """Resize sprite by ratio or percent, preserving aspect ratio."""
    factorX = SCALE_RATIO if SCALE_RATIO is not None else SCALE_PERCENTX / 100
    factorY = SCALE_RATIO if SCALE_RATIO is not None else SCALE_PERCENTY / 100
    if factorX == 1 and factorY == 1:
        return image.copy()

    new_size = (
        max(1, int(image.get_width() * factorX)),
        max(1, int(image.get_height() * factorY)),
    )
    return pygame.transform.smoothscale(image, new_size)


def build_input_path(index: int) -> Path:
    return INPUT_DIR / INPUT_PATTERN.format(index)


def main():
    pygame.init()
    pygame.display.set_mode((1, 1), pygame.HIDDEN)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for i in range(FRAME_COUNT):
        sprite_path = build_input_path(i)
        if not sprite_path.exists():
            print(f"Skipping {sprite_path} (missing)")
            continue

        sprite = pygame.image.load(sprite_path.as_posix()).convert_alpha()
        cropped_sprite = crop_to_sprite(sprite)
        resized_sprite = resize_sprite(cropped_sprite)
        out_path = OUTPUT_DIR / f"{i}.png"
        pygame.image.save(cropped_sprite, out_path.as_posix())

    print("✅ Finished cropping and resizing sprites.")


if __name__ == "__main__":
    main()