from pathlib import Path
import pygame


def _sort_key(path: Path):
    try:
        return int(path.stem)
    except ValueError:
        return path.stem


def load_frames_from_directory(directory: Path, scale=None, limit=None):
    """Load and optionally scale every frame inside *directory*."""
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"Animation directory not found: {directory}")

    frame_paths = sorted(directory.glob("*.png"), key=_sort_key)
    if not frame_paths:
        raise ValueError(f"No .png frames found inside {directory}")

    if limit:
        frame_paths = frame_paths[:limit]

    frames = []
    for path in frame_paths:
        surface = pygame.image.load(path.as_posix()).convert_alpha()
        if scale:
            if isinstance(scale, (tuple, list)):
                surface = pygame.transform.smoothscale(surface, scale)
            else:
                new_size = (
                    int(surface.get_width() * scale),
                    int(surface.get_height() * scale),
                )
                surface = pygame.transform.smoothscale(surface, new_size)
        frames.append(surface)

    return frames


def load_frames_from_spritesheet(
    sheet_path: Path,
    frame_width: int,
    frame_height: int,
    *,
    columns: int | None = None,
    rows: int | None = None,
    frame_count: int | None = None,
    scale=None,
):
    """Slice frames from a sprite sheet image.

    The sheet is iterated row-by-row. Supply frame dimensions plus optional
    columns/rows; if omitted, they are inferred from the sheet size. The
    *scale* argument matches :func:`load_frames_from_directory`.
    """

    sheet_path = Path(sheet_path)
    if not sheet_path.exists():
        raise FileNotFoundError(f"Sprite sheet not found: {sheet_path}")

    sheet = pygame.image.load(sheet_path.as_posix()).convert_alpha()
    sheet_width, sheet_height = sheet.get_size()

    columns = columns or max(1, sheet_width // frame_width)
    rows = rows or max(1, sheet_height // frame_height)
    total_frames = columns * rows
    if frame_count is not None:
        total_frames = min(total_frames, frame_count)

    frames = []
    for row in range(rows):
        for col in range(columns):
            if len(frames) >= total_frames:
                break
            rect = pygame.Rect(
                col * frame_width,
                row * frame_height,
                frame_width,
                frame_height,
            )
            frame = pygame.Surface(rect.size, pygame.SRCALPHA)
            frame.blit(sheet, (0, 0), rect)
            if scale:
                if isinstance(scale, (tuple, list)):
                    frame = pygame.transform.smoothscale(frame, scale)
                else:
                    new_size = (
                        int(frame.get_width() * scale),
                        int(frame.get_height() * scale),
                    )
                    frame = pygame.transform.smoothscale(frame, new_size)
            frames.append(frame)
        if len(frames) >= total_frames:
            break

    return frames


class SpriteAnimation:
    """Minimal animation controller for sprite frame lists."""

    def __init__(self, frames, frame_duration=0.1, loop=True):
        if not frames:
            raise ValueError("SpriteAnimation requires at least one frame")

        self.frames = frames
        self.frame_duration = frame_duration
        self.loop = loop
        self.current_index = 0
        self.time_accumulator = 0.0
        self.finished = False

    def update(self, dt: float):
        if self.finished:
            return
        self.time_accumulator += dt
        while self.time_accumulator >= self.frame_duration:
            self.time_accumulator -= self.frame_duration
            self.current_index += 1
            if self.current_index >= len(self.frames):
                if self.loop:
                    self.current_index = 0
                else:
                    self.current_index = len(self.frames) - 1
                    self.finished = True
                    break

    def reset(self):
        self.current_index = 0
        self.time_accumulator = 0.0
        self.finished = False

    @property
    def image(self):
        return self.frames[self.current_index]
