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
- `main.py` — entry point, instantiates and runs Game
- `game.py` — core game loop, event handling, draw; `update()` is a placeholder
- `assets.py` — TMX tilemap + background image loading (pytmx)
- `settings.py` — constants (window size, FPS, paths)
- `Assets/maps/level 1.tmx` — 40×30 tile map (32px tiles), single ground layer
- `tilesets/tilesets/` — multiple tileset PNGs available (A2_Ground in use)

**Missing:** Player, Tile grid, game mechanics, collision, UI — everything gameplay.

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
- Grid: 10×6 tiles at 64×64px = 640×384px, centered at (320, 168) on 1280×720
- Visuals: Pixel-art/custom assets (to be provided)
- Players: 1 player for Week 1

### Classes to Build
- `Tile` — state (NORMAL/WARNING/DISAPPEARED), timer, draw
- `TileGrid` — 10×6 grid, random disappear scheduler, update/draw
- `Player` — position (snapped to tile), input handling, fall detection, animations
- Update `Game.update()` + `Game.draw()` to drive all the above

### Tile State Machine
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
