# Tile Survival — Development Plan

## Project Overview
A multiplayer survival game where players stand on a tile-based platform.
Tiles randomly disappear (with a warning animation first), and players must
survive as long as possible. Difficulty scales over time. Built with Python
and Pygame.

## Tech Stack
- Game: Python + Pygame
- Networking: Python Socket Programming
- Website: React + Node.js + Express.js
- Analytics: Google Analytics

## Current State (as of March 2026)
Foundation phase complete:
- `main.py` — entry point, orchestrates scene flow (`TitleScreen` → `ModeSelectionScreen` → `GameManager`)
- `game.py` — core game loop (`GameManager` class) handling TMX map rendering, animated water, and updating players/AI
- `scenes.py` — UI screens (Title and Mode Selection) with particle effects and fading transitions
- `player.py` — physics, sub-pixel scaling, masking/bounds logic (`_is_over_platform`), and sprite animations
- `ai_player.py` — AI integration utilizing lookahead vector raycasting against the `walkable_mask` to navigate the TMX map
- `settings.py` — robust configuration constants (physics, `WALKABLE_LAYER_NAMES`, UI styling, particles)
- `assets.py` — TMX tilemap loading (`pytmx`) + background/water animations
- `Assets/maps/level 1.tmx` — remote TMX architecture serving as the foundational playable area

**Recent Architectural Shifts:**
- Pivot from a strict 2D array tile grid to pixel-precise `walkable_mask` collisions based on TMX layers.
- Resolved large merge conflicts by retaining the remote animated water and TMX rendering pipeline.
- Re-implemented AI and Player logic onto the new TMX architecture using masks instead of array indices.
- Implemented a 2-stage pre-game scene flow before diving into gameplay.

---

## Week 1 — Core Prototype

### Goals
- [x] Project setup, Pygame env, game window, game loop
- [x] Player movement (left/right/up/down) + pixel-art sprite animations
- [x] 10×6 tile grid platform (64px tiles), centered on screen
- [x] Tile state machine: Normal → Warning (flashing) → Disappeared
- [x] Random tile disappearance logic
- [x] Player fall/elimination when standing tile disappears
- [x] Single player (1 player only)

### Design Decisions
- Grid/Map System: Moving away from arbitrary 2D arrays to vector-based, pixel-precise `walkable_mask` collision driven by `pytmx` Object layers ("Platforms").
- Visuals: TMX Map, Animated Water layers (`Assets/maps/level 1.tmx`), and character sprite sheets containing run, jump, drown.
- UI: Sequential front-end (`TitleScreen` → `ModeSelectionScreen`) implemented to handle state before the core loop starts.
- Mechanics: Custom sub-pixel scaling and gravity calculations handle jumps, movement, and bounds checking (`_is_over_platform()`).

### Classes / Structure (Built and Working)
- `scenes.py` — `TitleScreen` and `ModeSelectionScreen`
- `ai_player.py` — Vector raycasting for pathfinding over TMX walkable masks
- `Player` — position, input handling, physics (jump, sub-pixel gravity), rendering sprites
- `GameManager` (formerly `Game`) — drives UI flow, TMX map rendering, and updates
- `settings.py` — Constants configuration

### High-Priority PENDING AUDIT (Integrating legacy array concepts into TMX Masking without breaking pipeline)
- Dynamic Tile disappearance system logic built over the TMX object layer.
- Ensure Tile State Machine visuals are supported (Warning → Disappeared).

### Tile State Machine (Pending adaptation to TMX)
```
NORMAL ──(timer expires)──> WARNING ──(flash duration)──> DISAPPEARED
  ^                                                             |
  └──────────────── (respawn / new round) ─────────────────────┘
```

---

## Week 2 — Gameplay Expansion

### Goals
- [x] Jump mechanics + improved physics (gravity, landing)
- [x] Local multiplayer (2 players: WASD + Arrow keys)
- [x] Hazard system: bullets + moving traps
- [x] Difficulty scaling system (faster disappearance, more simultaneous tiles)
- [x] Visual feedback (score, survival timer, elimination screen)
- [x] Bug fixes

---

## Week 3 — AI & Multiplayer

### Goals
- [x] Basic AI player (avoids disappearing tiles, random safe-tile movement)
- [ ] LAN multiplayer via Python sockets (non-blocking)
- [ ] Player state synchronization across network
- [ ] Networking bug fixes + optimization

---

## Week 4 — Website & Deployment

### Goals
- [ ] Deployment website (React + Node.js + Express)
- [ ] Download page
- [ ] Leaderboard system
- [ ] Analytics integration (Google Analytics)
- [ ] Game data connected to website

---

## Coding Conventions
- Clean, modular, well-commented Python
- Separate concerns: `Player`, `Tile`, `TileGrid`, `Hazard`, `GameManager` classes
- `settings.py` for all config values (tile size, speed, colors, timers)
- Each feature self-contained and independently testable
- Prioritize playable, non-broken states at every commit
- Networking: non-blocking sockets, handle disconnections gracefully
- AI: start simple (random safe tile), improve iteratively
