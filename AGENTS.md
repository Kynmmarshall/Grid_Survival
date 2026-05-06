# Repository Guidelines

## Project Overview

Grid Survival is an isometric tile-based survival game built with Pygame (Python 3.10+, 3.11 recommended). Players survive on collapsing platforms with character powers, orb buffs, LAN/internet multiplayer, and AI opponents.

## Project Structure & Module Organization

Core gameplay systems live at the top level and are imported directly:

- **`main.py`** — entry point; orchestrates scene transitions, account portal, and online setup flow
- **`game.py`** — `GameManager`; central game loop and state
- **`player.py`**, **`powers.py`**, **`orbs.py`**, **`hazards.py`**, **`tile_system.py`**, **`water.py`** — gameplay systems
- **`settings.py`** — single source of truth for all tunable constants (speeds, paths, HUD styling, orb/power config); edit here, not in gameplay code
- **`network.py`** — compatibility import facade over `online_play/`; do not add logic here

**`online_play/`** — layered networking stack (keep these layers separate):
- `transport.py` — UDP delivery, ACK/resend, fragmentation, liveness
- `session.py` — LAN discovery, `NetworkHost`/`NetworkClient`, UPnP, public IP
- `match_flow.py` — message schemas, payload builders/parsers for game setup

**`scenes/`** — full-screen menu flows (title, mode select, character select, account portal, etc.)

**`presentation/`** — HUD wrappers (`hud.py`, `player_card.py`, `prompts.py`, `waiting_screen.py`)

**`backend/`** — VPS-side server processes:
- `vps_sync_server.py` — account sync HTTP API
- `vps_control_plane.py` — lobby/matchmaking control plane (port 8010)
- `match_daemon.py` — match lifecycle daemon
- `account_service.py` — SQLite-backed account logic (shared by client and server)

**`Assets/`** — art, audio, TMX maps, fonts. Keep the folder structure intact; `settings.py` references asset paths directly.

## Build, Test, and Development Commands

```bash
# Install dependencies
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Run the game
python main.py

# Run all tests
pytest -q

# Run a single test file
pytest test_network.py -q

# Run backend VPS sync server
python -m backend.vps_sync_server

# Run backend control plane (matchmaking)
python -m backend.vps_control_plane

# Backend integration test (requires control plane running)
python -m backend.integration_test
```

CI runs `pytest -q` on both Linux and Windows (Python 3.11) on every push and weekly.

## Coding Style & Naming Conventions

No enforced linter or formatter config is present. Follow the existing style observed in the codebase:

- `snake_case` for functions, variables, and modules
- `PascalCase` for classes
- `ALL_CAPS` for module-level constants in `settings.py`
- `from __future__ import annotations` at the top of networking modules
- Type hints used throughout `online_play/` and `backend/`; match this pattern in new code

## Testing Guidelines

Framework: **pytest** (no `unittest.TestCase` subclassing in new tests — existing `test_network.py` uses `unittest` for legacy reasons).

- `test_network.py` — unit tests for `online_play/` transport, session, and match flow layers
- `backend/integration_test.py` — integration test requiring a live control plane; not run by CI automatically

Run all tests from the project root: `pytest -q`

## Environment Variables

| Variable | Purpose |
|---|---|
| `GRID_SURVIVAL_API_URL` | VPS account sync endpoint (optional; local-only if unset) |
| `GRID_SURVIVAL_ONLINE_API_KEY` | API key for control plane auth |
| `GRID_SURVIVAL_BORDERLESS` | Set to `1` to use a borderless window |
| `GRID_SURVIVAL_VPS_HOST/PORT/DB` | Server-side bind address, port, and DB path |

Copy `.env.example` to `.env` in the repo root for local configuration.

## Architecture Notes

- Always run the game from the project root so package imports resolve correctly.
- `settings.py` is the only place to change gameplay tuning — do not hardcode constants elsewhere.
- The `online_play/` stack has three strict layers (transport → session → match flow). Do not import upward (e.g., `session.py` must not import from `match_flow.py`).
- `network.py` is a compatibility shim; new code should import from `online_play/` directly.
- Asset paths are case-sensitive on Linux; match the `Assets/` directory casing exactly.
