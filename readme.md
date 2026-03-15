# GRID SURVIVAL

Grid Survival is a small isometric survival vignette built with Pygame. Guide a caveman across floating platforms, mind the gaps, and avoid the animated shoreline—once you miss a step and tumble into the surf, a one-shot death animation plays while the body sinks beneath the waves.

---

## Features

- **Layered isometric map rendering** powered by Tiled TMX data and `pytmx`, scaled to a 1280×720 window.
- **Directional caveman animation set** (idle, run, death) with smooth frame timing and pixel-perfect walkable collision masks.
- **Dynamic falling/drowning states** that determine whether the character renders in front of or behind the tilemap.
- **Animated shoreline** with looping water tiles plus a one-off splash effect triggered exactly where the player hits the surface.
- **Configurable debug overlays** for inspecting walkable regions, footboxes, and collision behavior during development.

---

## Controls

| Key | Action |
| --- | ------ |
| `W` `A` `S` `D` | Move the player |
| `L` | Reset the player to the starting platform |
| `ESC` | Exit the game |

---

## Getting Started

### Requirements

- Python 3.10+ (3.11 recommended)
- `pip` capable of installing wheel packages

### Installation

```bash
git clone <your-fork-or-clone-url>
cd Grid_Survival
python -m venv .venv
.venv\Scripts\activate  # PowerShell / Command Prompt
pip install --upgrade pip
pip install pygame pytmx
```

### Run the game

```bash
python main.py
```

> **Tip:** Keep the asset folder structure intact—`settings.py` points directly to the bundled art, TMX map, and spritesheets.

---

## Project Structure

```
Grid_Survival/
├─ Assets/                # Backgrounds, characters, TMX map, water spritesheets
├─ animation.py          # Sprite sheet + frame directory loaders, animation controller
├─ assets.py             # TMX renderer and walkable mask creation
├─ game.py               # Game loop, event handling, draw/update orchestration
├─ main.py               # Entry point that boots the Game wrapper
├─ player.py             # Player state machine (movement, falling, drowning)
├─ settings.py           # Centralized constants and asset paths
├─ water.py              # Animated shoreline and splash trigger
└─ readme.md             # Project documentation
```

---

## Configuration

Tweak [settings.py](settings.py) to adjust gameplay without touching code:

- **Player feel:** `PLAYER_SPEED`, `PLAYER_FALL_GRAVITY`, `PLAYER_FALL_MAX_SPEED`, `PLAYER_SINK_SPEED`.
- **Animation pacing:** `PLAYER_FRAME_DURATION`, `PLAYER_SCALE`.
- **Walkable logic:** `WALKABLE_LAYER_NAMES`, `WALKABLE_OBJECT_CLASS_NAMES`, `WALKABLE_ISO_TOP_FRACTION`.
- **Water presentation:** `WATER_TARGET_HEIGHT`, frame sizes/counts, sprite file paths.

Flip `DEBUG_VISUALS_ENABLED` and the related toggles to visualize masks and collision boxes while tuning.

---

## Troubleshooting

- **Black screen or missing map:** Confirm `pytmx` is installed and the TMX file referenced by `MAP_PATH` exists.
- **Water or character not visible:** Check that the asset directories referenced in `settings.py` match your local filesystem casing.
- **Collision feels off:** Enable the walkable debug overlay (`DEBUG_VISUALS_ENABLED = True`) to inspect the generated mask while adjusting Tiled layers.

Have fun experimenting with new hazards, animations, or tilemaps! Contributions are welcome—open an issue or PR with ideas for expanding the survival experience.