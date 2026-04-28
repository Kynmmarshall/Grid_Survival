# Grid Survival - Multi-PC Setup Guide

This guide helps you run Grid Survival on a new machine and connect to the online VPS.

## Quick Start (5 minutes)

### 1. Clone & Install Dependencies
```bash
# Clone the repo
git clone <repo-url> Grid_Survival
cd Grid_Survival

# Create virtual environment
python -m venv .venv

# Activate it
# Windows:
.\.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment (Important!)
Copy the example environment file:
```bash
cp .env.example .env
```

Open `.env` and verify the values match your VPS:
```
GRID_SURVIVAL_ONLINE_API=http://38.242.246.126:8010
GRID_SURVIVAL_ONLINE_API_KEY=a2fcb46811703d361f5074c6c86f01d6a241f30960b4176d4d924b90763822f2
```

> **The error "[WinError 10061] No connection could be made" usually means the `.env` file is missing or the variables aren't set, causing the client to try connecting to `localhost:8010` instead of the VPS.**

### 3. Run the Game
```bash
python main.py
```

Select: **ONLINE MULTIPLAYER** → **INTERNET** → Configure & Play

---

## Full Setup Details

### Python Requirements
- **Python 3.11+** (tested on 3.11.9 and 3.12.3)
- `pip install -r requirements.txt` installs:
  - `pygame==2.6.1` - Game engine
  - `requests` - HTTP client for lobby API
  - `python-dotenv` - Load environment variables from `.env`
  - `miniupnpc` - Optional UPnP support for LAN

### Environment Variables

#### Client (.env in repo root)
The client needs to know where to find the control-plane API:

| Variable | Value | Notes |
|----------|-------|-------|
| `GRID_SURVIVAL_ONLINE_API` | `http://38.242.246.126:8010` | VPS control-plane URL (HTTP) |
| `GRID_SURVIVAL_ONLINE_API_KEY` | (see backend/.env) | API authentication key |

#### VPS (backend/.env - only if hosting your own VPS)
If you're setting up a new VPS, see [VPS_SETUP.md](VPS_SETUP.md).

### How Environment Loading Works
1. Client startup calls `OnlineService.from_env()`
2. Loads `.env` file from repo root (if present)
3. Falls back to shell environment variables
4. Falls back to `http://127.0.0.1:8010` (localhost - won't work for internet play)

**→ If you get connection refused, ensure `.env` exists in the repo root.**

---

## Troubleshooting

### "Internet control-plane unavailable: [WinError 10061]"
**Root cause**: Client can't reach the VPS endpoint.

**Fixes**:
1. **Verify `.env` exists in repo root**: `ls .env`
   - If missing: `cp .env.example .env`
2. **Check VPS is running** (from VPS terminal):
   ```bash
   sudo systemctl status grid-survival-control.service
   sudo ss -tlnp | grep 8010  # Should show LISTEN 0.0.0.0:8010
   ```
3. **Check network connectivity** (from your PC):
   ```bash
   # Windows:
   Test-NetConnection -ComputerName 38.242.246.126 -Port 8010
   
   # Mac/Linux:
   nc -zv 38.242.246.126 8010
   ```
4. **Firewall**: Ensure outbound to 38.242.246.126:8010 (TCP) and :5555 (UDP) is open

### "ModuleNotFoundError: No module named 'pygame'"
```bash
pip install --upgrade -r requirements.txt
```

### "Connection refused" on UDP socket
- This is normal during initial connection attempts
- Client retries 3 times automatically
- If persists, check:
  - VPS daemon running: `sudo ss -ulnp | grep 5555`
  - Firewall: `sudo ufw status | grep 5555`

### Game runs but can't join lobby
- Enable debug logging:
  ```bash
  set GRID_SURVIVAL_DEBUG_ONLINE=1
  python main.py
  ```
- Look for: `[DEBUG] OnlineService.from_env -> base_url=...`
- If base_url shows `127.0.0.1`, then `.env` wasn't loaded

---

## Platform-Specific Notes

### Windows
- Use `.\.venv\Scripts\activate` to activate venv
- Firewall: Windows Defender usually allows outbound connections by default
- Can SSH to VPS using PuTTY or native `ssh` command (PowerShell 7+)

### Mac/Linux
- Use `source .venv/bin/activate` to activate venv
- If SDL2 issues: `brew install sdl2` (Mac) or `sudo apt install libsdl2-2.0` (Ubuntu)

---

## Setting Up Your Own VPS

If hosting on a new VPS, see [VPS_SETUP.md](VPS_SETUP.md) for:
- Installing dependencies
- Starting the control-plane and match daemon
- Configuring firewall (ufw)
- Systemd service setup

---

## Verification Checklist

Before playing on internet mode:
- [ ] Python 3.11+ installed
- [ ] `.venv` created and activated
- [ ] `pip install -r requirements.txt` completed
- [ ] `.env` file exists in repo root
- [ ] `.env` has correct `GRID_SURVIVAL_ONLINE_API` and `GRID_SURVIVAL_ONLINE_API_KEY`
- [ ] Network can reach VPS (test with `ping` or `nc`)
- [ ] VPS services are running (`grid-survival-control.service` status)
- [ ] Game starts: `python main.py`

---

## Need Help?

Check for error logs:
- **Client-side**: Look at console output for `[DEBUG]` messages (enable with `GRID_SURVIVAL_DEBUG_ONLINE=1`)
- **VPS-side**: `sudo journalctl -u grid-survival-control.service -f`
