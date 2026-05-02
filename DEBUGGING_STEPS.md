# Online Game Freeze Debugging Steps

## Overview
The client freezes ~5 seconds after connecting to online play, and the server continues sending snapshots even after the client exits.

## Diagnostic Changes Made
1. **Client-side (game.py):**
   - Added snapshot reception logging to track messages arriving from server
   - Added frame timing diagnostics every 0.5s to detect if game loop is freezing
   - Added network queue depth monitoring

2. **Server-side (match_daemon.py):**
   - Added CLIENT_TIMEOUT = 30s to detect and stop sending to inactive clients
   - Modified hello handler to track last_seen timestamps
   - Modified snapshot loop to skip stale clients after timeout

## Step-by-Step Debugging

### STEP 1: Run Server with Diagnostics
```bash
ssh root@38.242.246.126
cd /root/grid-survival-vps/backend
python match_daemon_main.py
```
- **Watch for:** Server should bind to :5555 and be ready to receive clients
- **Look for:** `[DEBUG] MatchDaemon.run -> bound to 0.0.0.0:5555`

### STEP 2: Run Client and Play ~10 Seconds
```bash
# In separate terminal on your local machine:
cd c:\Users\kynm\Desktop\Grid_Survival
python main.py
```
- Select **Online Multiplayer** mode
- Enter credentials and connect to 38.242.246.126:5555
- **Play for ~10 seconds** (this is when freeze should occur)
- Let it run for another ~5 seconds after freeze appears
- **Exit cleanly** (Alt+F4 or Ctrl+C)

### STEP 3: Collect Diagnostic Output

**On CLIENT terminal, look for:**
```
[DIAG] ProcessMessages: got N messages, types={...}, snap=True, world_snap=True
[DIAG] Frame XXX: dt=X.Xms, elapsed=X.Xms, status=CONNECTED, queue_depth=N
```
- **If snap=True → snapshots ARE arriving**
- **If snap=False → NO snapshots arriving (network issue)**
- **If queue_depth increases → messages backing up (processing too slow)**
- **If elapsed > 20ms → frame is taking too long**

**On SERVER terminal, look for:**
```
[DEBUG] MatchDaemon.recv from (143.105.152.147, 32041)
[DEBUG] MatchDaemon.sent -> kind=d to=(...) seq=XXXX type=snapshot
[DEBUG] MatchDaemon: skipping stale client ... (last_seen X.Xs ago)
```
- **If snapshots still sending after you exit → client timeout NOT detected**
- **If it says "skipping stale client" → timeout working, client was detected as dead**

## Key Indicators

### Scenario A: Snapshots NOT Arriving (snap=False)
- **Problem:** Network receive is broken
- **Next step:** Check socket connectivity in transport.py
- **Investigate:** Is `_receive_loop()` still running? Is socket closed unexpectedly?

### Scenario B: Snapshots Arriving (snap=True) but Freeze Persists
- **Problem:** Game logic freeze after snapshot applied
- **Next step:** Check if `_apply_network_snapshot()` is blocking
- **Investigate:** Is snapshot too large? Is player update expensive?

### Scenario C: Frame timing shows elapsed >> dt
- **Problem:** GPU/render is blocked (drawing takes too long)
- **Next step:** Check draw() method performance
- **Investigate:** Are we redrawing every frame unnecessarily?

### Scenario D: queue_depth keeps growing
- **Problem:** Messages arriving faster than being processed
- **Next step:** Optimize message processing
- **Investigate:** Is network layer sending duplicates? Is processing too slow?

## Expected Behavior After Fix

✅ **Snapshots should arrive continuously:** `snap=True` every frame
✅ **Frame timing should be ~16ms:** `elapsed≈16ms` at 60 FPS
✅ **Queue depth should stay ~0-1:** Messages processed immediately
✅ **Server should stop sending after 30s of no client data:** `skipping stale client` appears in logs

## Quick Reference: Log Patterns

| Pattern | Means |
|---------|-------|
| `snap=True` | Snapshot received ✅ |
| `snap=False` (repeatedly) | NO snapshots arriving ❌ |
| `queue_depth=0-1` | Processing fine ✅ |
| `queue_depth > 5` | Backing up ❌ |
| `elapsed < 17ms` | Frame timing good ✅ |
| `elapsed > 20ms` | Frame too slow ❌ |
| `skipping stale client` | Server timeout working ✅ |

---

## Report Format

When sharing results, include:
1. **First 3 lines of client [DIAG] output when connected**
2. **First and last [DIAG] Frame line during freeze**
3. **Server output showing snapshot sends and any timeout messages**
4. **When you exited, did server say "skipping stale client"?**

This will help identify where the freeze is happening!
