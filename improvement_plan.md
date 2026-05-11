# Grid Survival — Improvement Plan

## Goals (based on your feedback)
1. Fix **power visuals/behaviour** so abilities appear to originate from (and aim with) the character’s movement/face direction (not “anywhere”).
2. Verify and fix **online lobby / LAN lobby** issues.
3. Improve **multiplayer network consistency** (tile/hazard/orb/projectile/power visuals) so clients look like the host.
4. Add a more “modern games” **intro video/trailer** shown on launch.
5. Recommend additional “modern” improvements to attract more players.

---

## Current Systems (high level)
- **Entrypoint / scene flow**: `main.py` → scene classes in `scenes/` → `GameManager` in `game.py`
- **Game loop**: `GameManager.run()` → `handle_events()` → `update(dt, keys)` → `draw()`
- **Map & walkability**: `assets.py` (TMX render + walkable mask)
- **Destructible tiles**: `tile_system.py` (`TMXTileManager` + `TMXTile` state machine + particles)
- **Players**: `player.py` (movement + jump Z + falling/drowning + shield/orbs)
- **Powers**: `powers.py` (character powers + network snapshot hooks)
- **Hazards**: `hazards.py` (bullets/traps/animated hazards/explosions)
- **Projectiles**: `projectiles.py` (projectile visuals + knockback + monster hits)
- **Orbs**: `orbs.py` (spawn/collect + orb effects)
- **Online**:
  - Session setup flow: `online_play/session_flow.py`
  - Transport/session layer: `online_play/session.py`, `online_play/transport.py` (via `network.py`)
  - In-game sync & snapshots: `game.py`

---

## 0) Investigation checklist (do before changing behaviour)
- [ ] Reproduce the “power appearing anywhere” bug in:
  - [ ] Local campaign
  - [ ] Local multiplayer (2 players)
  - [ ] Online/LAN host + joining client
- [ ] Identify which power(s) mis-render/ mis-aim:
  - [ ] Archer (Volley) arrows?
  - [ ] Ninja (Shadow Dash) target cursor / landing?
  - [ ] Knight (Shield Bash) tile smash direction?
  - [ ] Caveman (Ground Smash) shockwave direction/ring?
  - [ ] Samurai (Blade Storm) ring/particles direction?
  - [ ] Wizard freeze visuals?
- [ ] Identify online lobby issue symptoms:
  - [ ] Can you host?
  - [ ] Can you join?
  - [ ] Does “syncing characters” work?
  - [ ] Do matches start for both clients?
  - [ ] Any disconnects / timeouts?
- [ ] Run existing test suite (at least `test_network.py`) and record results.

---

## 1) Network state completeness (authoritative vs cosmetic)
**Problem statement:**  
Tile/hazard/orb/projectile sync exists, but some effects appear locally only (e.g. tile debris particles cleared on snapshot apply; explosions/FX and certain power visuals may diverge).

### 1.1 Decide authority model for effects
We should choose, per effect category:
- **Authoritative visuals** (must match host exactly):
  - Tile *state overlays* (warning/crumble/fall/alpha) — already snapshot via tile state
  - Hazard movement + positions if those affect outcomes (bullets/traps positions)
- **Cosmetic visuals** (may differ without breaking gameplay):
  - Debris particles spawned *when* warning starts/crumble starts (can be treated as cosmetic if tile state is synced)
  - Explosion particle FX that do not affect collisions (purely visual)
  - UI notifications (“POWER READY”, orb notifications)

### 1.2 What to fix first (low risk, high value)
- [ ] **Tile debris particles**:
  - Currently, client snapshot apply clears `tile.particles`, and debris is spawned only in `_start_crumble()` on host.
  - Decide:
    - [ ] Option A (cosmetic): don’t expect debris to match; ensure tile overlay timing is correct.
    - [ ] Option B (better): add snapshot data or an “FX event” for debris start (host sends “tile_crumble_fx” events or includes a “crumble_started_at” timestamp so client can re-run particles deterministically).
- [ ] **Power cosmetic/state completeness**:
  - Some powers snapshot only partial state.
  - Example concerns found in code review:
    - `ArcherPower`: `_arrows` lifetime updates, but arrow positions may not be advanced over time (visual drift / “not projected” issues).
    - `CavemanPower`: shockwave ring is visual but not fully synchronized via snapshot hooks.
  - Fix plan:
    - [ ] Ensure every power that draws direction-dependent visuals has enough snapshot state to render correctly on clients.
    - [ ] Ensure any projectile-like power (Archer arrows) updates positions consistently (host and client).
- [ ] **Projectile visual reconciliation**:
  - Projectiles may be treated as cosmetic replicas on clients; ensure `apply_snapshot()` provides enough data and clients don’t run authoritative collisions for replicas.
  - Validate that power knockback/eliminations still occur only via host logic.

### 1.3 Instrumentation for debugging desync
- [ ] Add debug overlays/logging (toggleable) to display:
  - Tile count in each state (NORMAL/WARNING/CRUMBLING/FALLING/DISAPPEARED)
  - Whether snapshot apply occurred this frame
  - Power active state + facing direction + any aiming vectors
- [ ] On mismatch, dump a small snapshot summary to a log.

### 1.4 Success criteria
- [ ] Joining client sees the same tile overlays at the same times as host.
- [ ] Directional power visuals attach correctly to the character’s facing/target direction.
- [ ] No gameplay desync: wins/eliminations/round transitions must be consistent.

---

## 2) Fix “power appearing anywhere” + direction projection
**Observed symptom:**  
When playing and using character powers, the power appears anywhere and not projecting from where the character is moving/facing.

### 2.1 Reproduce and classify
- [ ] Identify powers that break (start with Archer + Knight since direction/aim is involved).
- [ ] Identify if bug is only online/LAN, or also offline.

### 2.2 Likely causes (from code review)
- [ ] **ArcherPower**: arrows may be drawn at stale positions because arrows aren’t updated along their direction each frame.
- [ ] **Network power snapshot** may not include all state needed for visual placement (e.g., aiming origin, facing vector, and in-progress visual timers).
- [ ] **KnightPower** bash direction:
  - smash tile selection should be consistent with `owner.facing`, and snapshots must preserve `_bashed` state only if visuals depend on it.

### 2.3 Fix plan
- [ ] Implement correct visual evolution for power effects:
  - Arrow-based powers: update arrow positions in `update()` based on direction * speed * dt.
  - Direction-based powers: ensure visual draw uses the same facing/target origin used by `apply_to_game`.
- [ ] Extend `snapshot_power_state()` for affected powers:
  - Include origin/facing vector + any dynamic timers used by `draw()`.
- [ ] Validate locally and with 2-player LAN and online join.

### 2.4 Success criteria
- [ ] Power visuals always originate from the character’s current position/facing (or intended aim target).
- [ ] Direction is consistent across host + joining client.

---

## 3) Check and fix online lobby / session flow
### 3.1 What to verify
- [ ] `online_play/session_flow.py`:
  - character selection exchange
  - expected player count handling
  - host initiating `game_start`
- [ ] `online_play/internet_party_lobby.py` and lobby UI scenes:
  - “ready” toggles
  - match assignment and token/endpoint exchange
- [ ] Transport layer connection:
  - ensure host/listener starts correctly
  - ensure reconnect/disconnect handling doesn’t break match start

### 3.2 Likely areas to inspect next
- [ ] `scenes/internet_party_lobby.py`
- [ ] `online_play/internet_session.py`
- [ ] `online_play/lan_lobby_session.py`
- [ ] `online_play/transport.py` (packet types, disconnect detection)

### 3.3 Success criteria
- [ ] Lobby reliably starts matches for host + joiner.
- [ ] Joining client’s round transition and RR reward are correct.

---

## 4) Modern intro video/trailer on launch
### 4.1 Define format
- [ ] 10–25 seconds intro loop or “Play once then proceed”
- [ ] Show “skip” option
- [ ] Must work in:
  - [ ] source run (`python main.py`)
  - [ ] packaged build (if applicable)

### 4.2 Implementation approach options
- [ ] **Option A (simple):** use a short MP4 and render frames via `pygame` + ffmpeg-based preprocessing.
- [ ] **Option B (cleanest visuals):** generate a low-res animated video (e.g., 640p) and stream frames efficiently.
- [ ] **Option C (no video decode dependency):** create a “video-like” effect using pre-split frames + a sprite animation.

### 4.3 Success criteria
- [ ] Intro plays on launch without heavy CPU spikes.
- [ ] Skip works immediately (Esc).
- [ ] Transitions cleanly to title screen.

---

## 5) Additional “modern games” improvements (attractive features)
Pick a subset based on your preference:
- [ ] Add difficulty options + clearer onboarding tutorial inside lobby
- [ ] Add settings:
  - [ ] fullscreen/borderless toggle
  - [ ] motion blur / particles toggle
  - [ ] colorblind mode (alternate palette)
- [ ] Add accessibility:
  - [ ] subtitles for tutorial
  - [ ] remappable keys with an in-game UI (already have persistence)
- [ ] Add better social proof:
  - [ ] “player stats” badges, MVP highlight
  - [ ] post-match summary that shows meaningful metrics
- [ ] Add performance mode:
  - [ ] reduce particle density (server authoritative state remains unchanged)
- [ ] Add controller support if desired

---

## Execution order (recommended)
1. [ ] **Network state completeness** (start here)
2. [ ] Fix power visual direction projection bug
3. [ ] Validate online lobby flow
4. [ ] Implement intro video/trailer
5. [ ] Add modern attractiveness improvements
