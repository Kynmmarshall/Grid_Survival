# Grid Survival - VPS Setup Guide

This guide is for setting up a new VPS to host the control-plane and match daemon.

## Prerequisites
- Ubuntu 20.04+ (tested on Ubuntu 22.04)
- Python 3.11+
- SSH access to VPS

## Quick Setup (10 minutes)

### 1. Install Python & Git
```bash
sudo apt update && sudo apt install -y python3 python3-venv python3-pip git
```

### 2. Clone Repo
```bash
git clone <repo-url> grid-survival
cd grid-survival
```

### 3. Create Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure VPS Environment
Edit `backend/.env`:
```bash
# Copy and edit - use your VPS public IP
sudo nano backend/.env
```

Key values:
```
GRID_SURVIVAL_MATCH_ENDPOINT=udp://YOUR_PUBLIC_IP:5555
GRID_SURVIVAL_MATCH_BIND_ENDPOINT=udp://0.0.0.0:5555
GRID_SURVIVAL_CONTROL_HOST=0.0.0.0
GRID_SURVIVAL_CONTROL_PORT=8010
GRID_SURVIVAL_ONLINE_API_KEY=<your-secure-key>
```

### 5. Install Systemd Service
```bash
# Copy service file
sudo cp backend/grid-survival-control.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable grid-survival-control.service
sudo systemctl start grid-survival-control.service

# Verify status
sudo systemctl status grid-survival-control.service
```

### 6. Configure Firewall
```bash
sudo ufw allow 8010/tcp   # Control-plane HTTP API
sudo ufw allow 5555/udp   # Match daemon UDP
sudo ufw enable
```

### 7. Verify Services Running
```bash
# Check HTTP API
sudo ss -tlnp | grep 8010

# Check UDP daemon
sudo ss -ulnp | grep 5555

# Check logs
sudo journalctl -u grid-survival-control.service -f
```

## Troubleshooting

### Service fails to start
```bash
sudo journalctl -u grid-survival-control.service | tail -50
```

Common issues:
- **"Port already in use"**: Another service on 8010 or 5555. Stop it or use different ports.
- **"Permission denied"**: Run with `sudo` or ensure user owns the directory.

### Can't reach VPS from client
```bash
# From client, test:
nc -zv YOUR_VPS_IP 8010   # Should succeed
nc -zv YOUR_VPS_IP 5555   # May fail (UDP is connectionless), but ufw should allow it
```

If blocked:
- Check firewall: `sudo ufw status`
- Check service listening: `sudo ss -tlnp`
- Check VPS firewall provider (AWS, DigitalOcean, etc.)

### Match daemon not simulating bots/enemies
```bash
sudo journalctl -u grid-survival-control.service -f
# Look for: "[DEBUG] tick_bots" or "[DEBUG] _build_enemy_spawns"
```

---

## Files Overview

| File | Purpose |
|------|---------|
| `backend/vps_control_plane.py` | HTTP API server (lobby, queue, matchmaking) |
| `backend/vps_match_server.py` | Match assignment manager |
| `backend/match_daemon.py` | UDP authoritative game server (physics, bots, enemies) |
| `backend/online_service.py` | Client-side HTTP wrapper (loads .env) |
| `network.py` | Client-side UDP transport |

## Production Considerations

- **Auto-restart**: Systemd service has `Restart=always`
- **Logging**: Check `journalctl` for persistent logs
- **Performance**: Runs ~30 concurrent matches per daemon instance (tune based on CPU/RAM)
- **Scaling**: Deploy multiple match daemon instances on different ports; control-plane distributes matches
- **Security**: Change `GRID_SURVIVAL_ONLINE_API_KEY` to a strong random value

---

## Rollback

If deployment fails:
```bash
sudo systemctl stop grid-survival-control.service
# Fix issues in backend/.env or code
sudo systemctl start grid-survival-control.service
```
