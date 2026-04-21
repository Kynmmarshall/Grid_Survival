# GRID SURVIVAL

Grid Survival is an isometric survival game built with Pygame. Survive on floating platforms, use character powers and orb buffs, and stay off the collapsing tiles, hazards, and shoreline.

## Highlights

- Isometric TMX map rendering with dynamic tile disappearance and crumble effects.
- Multiple character powers, including Ground Smash, Shadow Dash, Arcane Freeze, Shield Bash, Overclock, Blade Storm, and Volley.
- Orb pickups with temporary buffs, including Void Walk so players can cross missing tiles for a short time.
- LAN multiplayer host/join flow plus AI opponents.
- Polished title, mode select, character select, HUD, and end screens.
- Player HUD cards with portraits, power status, orb status, and control hints.
- Debug overlays for walkable masks, footboxes, and collision behavior.

## Controls

| Key | Action |
| --- | --- |
| `W` / `A` / `S` / `D` | Player 1 move |
| `Arrow Keys` | Player 2 move |
| `Space` | Player 1 jump |
| `Right Shift` | Player 2 jump |
| `Q` | Player 1 power |
| `Slash` | Player 2 power |
| `L` | Reset the current run |
| `Enter` | Confirm menu selections |
| `Esc` | Back / quit |

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
pip install miniupnpc
```

### Run the game

```bash
python main.py
```

## Account System and Sync

The game now supports local account creation and optional VPS sync:

- Local account data is stored in SQLite (`player_accounts.db` in source runs, AppData in frozen builds).
- Each account tracks username, RR (ranked rating), wins, losses, MVP count, eliminations, deaths, and damage stats.
- At startup, the Account Portal allows login, account creation, profile view, and leaderboard view.
- Leaderboard is online-only (requires configured VPS API).
- During gameplay, stats and RR deltas are written locally first and queued for sync.
- When online, queued sync events are pushed to the VPS API automatically.

### Configure VPS endpoint

Set this environment variable before launching the game client:

```powershell
$env:GRID_SURVIVAL_API_URL = "http://<your-vps-host>:8000"
python main.py
```

If `GRID_SURVIVAL_API_URL` is not set, the game still works fully with local accounts only.

### Run the sample VPS sync API

This repository includes a lightweight server for external account sync:

```bash
python -m backend.vps_sync_server
```

Optional server environment variables:

- Preferred:
	- `GRID_SURVIVAL_VPS_HOST` (default `0.0.0.0`)
	- `GRID_SURVIVAL_VPS_PORT` (default `8000`)
	- `GRID_SURVIVAL_VPS_DB` (default `vps_accounts.db`)
- Backward-compatible aliases:
	- `DB_HOST`
	- `DB_PORT`
	- `DB_NAME`

If both styles are set, `GRID_SURVIVAL_VPS_*` takes precedence.

> Keep the asset folder structure intact. `settings.py` points directly to the bundled art, TMX map, fonts, and audio files.

## Project Structure

The codebase is now split into a few clearer areas:

```text
Grid_Survival/
├─ Assets/
├─ presentation/
│  ├─ __init__.py
│  ├─ hud.py
│  ├─ player_card.py
│  ├─ prompts.py
│  └─ waiting_screen.py
├─ scenes/
│  ├─ title_screen.py
│  ├─ mode_selection.py
│  └─ player_selection.py
├─ tools/
│  ├─ __init__.py
│  ├─ generate_sfx.py
│  └─ prepare_backgrounds.py
├─ animation.py
├─ assets.py
├─ audio.py
├─ character_manager.py
├─ collision_manager.py
├─ environment.py
├─ game.py
├─ hazards.py
├─ host_waiting_screen.py
├─ lan_prompts.py
├─ level_config.py
├─ main.py
├─ network.py
├─ orbs.py
├─ player.py
├─ playercard.py
├─ powers.py
├─ settings.py
├─ tile_system.py
├─ ui.py
├─ water.py
└─ readme.md
```

The `presentation/` package groups the user-facing UI wrappers, while `tools/` holds the utility scripts. Core gameplay systems still live at the top level for compatibility.

## Configuration

Tweak `settings.py` to adjust gameplay without touching code:

- Player feel: `PLAYER_SPEED`, `PLAYER_FALL_GRAVITY`, `PLAYER_FALL_MAX_SPEED`, `PLAYER_SINK_SPEED`.
- Animation pacing: `PLAYER_FRAME_DURATION`, `PLAYER_SCALE`.
- Walkable logic: `WALKABLE_LAYER_NAMES`, `WALKABLE_OBJECT_CLASS_NAMES`, `WALKABLE_ISO_TOP_FRACTION`.
- HUD and menu styling: font paths, panel colors, and spacing constants.
- Orb and power tuning: durations, cooldowns, and spawn frequency.

Flip `DEBUG_VISUALS_ENABLED` and the related toggles to inspect masks and collision boxes while tuning.

## Troubleshooting

- Black screen or missing map: confirm `pytmx` is installed and the TMX file referenced by `MAP_PATH` exists.
- Water or character not visible: check that the asset directories referenced in `settings.py` match your local filesystem casing.
- Collision feels off: enable the walkable debug overlay by setting `DEBUG_VISUALS_ENABLED = True`.
- Import errors after reorganizing files: run the game from the project root so the package imports resolve correctly.

Have fun experimenting with new hazards, animations, tilemaps, and powers.
