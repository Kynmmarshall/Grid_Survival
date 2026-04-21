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
Foundation phase complete, with major UI/UX polish implemented:

**Core Modules:**
- `main.py` — entry point, orchestrates scene flow (`TitleScreen` → `ModeSelectionScreen` → `GameManager`)
- `game.py` — core game loop (`GameManager` class) handling TMX map rendering, animated water, and updating players/AI
- `scenes.py` — UI screens (Title and Mode Selection) with particle effects and fading transitions
- `player.py` — physics, sub-pixel scaling, masking/bounds logic (`_is_over_platform`), and sprite animations
- `ai_player.py` — AI integration utilizing lookahead vector raycasting against the `walkable_mask` to navigate the TMX map
- `settings.py` — robust configuration constants (physics, `WALKABLE_LAYER_NAMES`, UI styling, particles)
- `assets.py` — TMX tilemap loading (`pytmx`) + background/water animations
- `tile_system.py` — TMX-based tile disappearance with states (Normal → Warning → Crumbling → Disappeared), debris particles, sound effects, and graceful period
- `ui.py` — Redesigned GameHUD with styled panels, elimination/victory screens with animations

**New Assets:**
- `Assets/sounds/` — `tile_warning.wav`, `tile_disappear.wav`, `player_fall.wav` (placeholder sounds)
- `Assets/fonts/` — directory ready for PressStart2P.ttf, Orbitron-Regular.ttf

**Recent Implementations (March 2026):**

1. **Tile Disappearance System (Category 1)**
   - Added `TileState.CRUMBLING` between WARNING and DISAPPEARED
   - `TILE_CRUMBLE_DURATION = 350ms` for smooth darkening transition
   - `DebrisParticle` class: 4–6 colored squares fly outward with gravity
   - Sound effects on warning and disappear triggers
   - 3-second grace period before first tile disappears
   - Polished void holes (dark diamond with subtle inner shadow)

2. **In-Game HUD Redesign (Category 2)**
   - Three styled panels: Score (gold border), Timer (white border), Alive (green/orange/red)
   - Arcade font hierarchy loaded from `assets/fonts/`
   - Timer urgency styling: red pulsing border/text when time is low
   - Score animation: scale to 120% + gold flash on increase
   - Alive counter color states: green → orange → red (last player)

3. **TitleScreen & ModeSelectionScreen Overhaul (Category 3)**

4. **Hazard & Physics Refinement (Category 4) - March 20**
   - **Fairer Hitboxes**: Implemented `get_hitbox()` in `Player` class to shrink collision rect by 40% (x and y), preventing "cheap" deaths.
   - **Death States**: Fixed a bug where players froze upon elimination. Added `die()` state transition and updated game loop to play death animations fully.
   - **Explosion Fix**: Optimized `Explosion.draw` in `hazards.py` to fix invisible shockwaves/particles and improve performance.
   - Font hierarchy: Display/Heading/Body/Small fonts with fallback
   - Title animation: letter drop with bounce, color cycling, periodic shake
   - Input box: rounded rect, gold border, blinking cursor
   - Mode cards: 460×145px with per-mode colored borders, hover lift, click scale
   - Header slide-in: "Welcome, [Name]!" slides down while fading

4. **Elimination & Victory Screen Fix**
   - Replaced overflowing `impact` 72px font with properly sized HUD font (42px)
   - Auto-scale safety: title shrinks if >80% screen width
   - Pulsing colored title with drop shadow
   - Centered panel card layout with stats
   - Blinking restart prompt after fade-in

5. **Physics & Effects Overhaul (Category 4)**
   - **2.5D Jumping**: Implemented Z-axis physics where players jump *up* visually while a shadow remains on the ground.
   - **Explosions**: Added shockwave rings and particle physics (drag, fading) for impactful hazard collisions.
   - **Audio Controls**: Mute button added to in-game HUD.
   - **Color Unification**: All UI/Game colors derived from a central `COLOR_PALETTE`.

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
