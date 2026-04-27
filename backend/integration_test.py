"""Integration test: create lobby, ready, enqueue, poll for match, then UDP auth.

Usage: set env GRID_SURVIVAL_CONTROL_HOST/PORT or pass args. Run while control-plane is running.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import time
from pathlib import Path
from urllib.parse import urljoin


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


SCRIPT_DIR = Path(__file__).resolve().parent
for candidate in (SCRIPT_DIR / ".env", SCRIPT_DIR.parent / "backend" / ".env", SCRIPT_DIR.parent / ".env"):
    _load_env_file(candidate)

CONTROL_HOST = os.getenv("GRID_SURVIVAL_CONTROL_HOST", "127.0.0.1")
CONTROL_PORT = int(os.getenv("GRID_SURVIVAL_CONTROL_PORT", "8010"))
API_KEY = (os.getenv("GRID_SURVIVAL_ONLINE_API_KEY") or os.getenv("GRID_SURVIVAL_CONTROL_API_KEY") or "").strip()
BASE = f"http://{CONTROL_HOST}:{CONTROL_PORT}"


def _auth_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["X-API-Key"] = API_KEY
    return headers


def http_post(path: str, payload: dict):
    url = urljoin(BASE + "/", path.lstrip("/"))
    import urllib.request
    import urllib.error

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=5.0) as r:
            raw = r.read()
            return r.getcode(), json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw.decode("utf-8")) if raw else {"ok": False, "error": str(e)}


def http_get(path: str):
    url = urljoin(BASE + "/", path.lstrip("/"))
    import urllib.request
    import urllib.error

    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=5.0) as r:
            raw = r.read()
            return r.getcode(), json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw.decode("utf-8")) if raw else {"ok": False, "error": str(e)}


def parse_endpoint(endpoint: str):
    e = endpoint
    if "://" in e:
        e = e.split("://", 1)[1]
    if "/" in e:
        e = e.split("/", 1)[0]
    host = "127.0.0.1"
    port = 5555
    if ":" in e:
        host, p = e.rsplit(":", 1)
        host = host or host
        try:
            port = int(p)
        except Exception:
            port = 5555
    if host in {"0.0.0.0", "::", ""}:
        host = "127.0.0.1"
    return host, port


def udp_send_recv(host: str, port: int, pkt: dict, timeout: float = 2.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(json.dumps(pkt).encode("utf-8"), (host, port))
        data, _ = s.recvfrom(65536)
        return json.loads(data.decode("utf-8"))
    finally:
        s.close()


def main():
    player = "test_alice"
    print("Creating lobby...")
    code = None
    status, data = http_post("/internet/lobbies/create", {"player": player, "mode": "ranked", "target_score": 3})
    print(status, data)
    if data.get("ok") and data.get("lobby"):
        code = data["lobby"]["code"]
    if not code:
        print("failed to create lobby")
        return 1

    print("Setting ready...")
    status, data = http_post("/internet/lobbies/ready", {"player": player, "lobby_code": code, "ready": True})
    print(status, data)
    print("Enqueueing...")
    status, data = http_post("/internet/queue/enqueue", {"player": player, "lobby_code": code, "region": "global"})
    print(status, data)

    print("Polling updates (waiting for match_found)...")
    match = None
    for _ in range(60):
        status, data = http_get(f"/internet/updates?player={player}")
        if data.get("ok"):
            events = data.get("events") or []
            for ev in events:
                if ev.get("type") == "match_found":
                    match = ev.get("match")
                    break
        if match:
            break
        time.sleep(1.0)
    print("match:", match)
    if not match:
        print("no match found in time")
        return 2

    join = match.get("join")
    endpoint = join.get("endpoint")
    token = join.get("token")
    print("Endpoint, token:", endpoint, token)

    host, port = parse_endpoint(endpoint)
    print("UDP target:", host, port)

    pkt = {"k": "d", "s": 1, "r": 0, "t": "internet_auth", "p": {"token": token, "player": player}}
    print("sending internet_auth...")
    try:
        resp = udp_send_recv(host, port, pkt, timeout=3.0)
        print("udp resp:", resp)
    except Exception as e:
        print("udp error:", e)
        return 3

    print("success")
    return 0


if __name__ == "__main__":
    sys.exit(main())
