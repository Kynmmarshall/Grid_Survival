from __future__ import annotations

import json
import math
import socket
import threading
import time
from typing import Any

from backend.vps_match_server import MatchServerManager
from network import PKT_DATA, PKT_FRAGMENT, PKT_HELLO, PKT_HELLO_ACK
from settings import PLAYER_START_POS


class MatchDaemon:
    """Authoritative UDP match daemon for assigned matches.

    Protocol (UDP JSON envelopes):
    - receives datagrams with JSON packet like {"k":"d","s":seq,"r":0,"t":"internet_auth","p":{...}}
    - responds with same envelope format for PKT_DATA messages.
    - supports messages: internet_auth, input_state, resync_request
    - emits snapshot, world_snapshot periodically.
    """

    def __init__(self, manager: MatchServerManager, bind_addr: str = "0.0.0.0", bind_port: int | None = None):
        self.manager = manager
        self.bind_addr = bind_addr
        self.bind_port = bind_port or 5555
        self.sock: socket.socket | None = None
        self.running = False
        self._lock = threading.Lock()
        self._sessions: dict[str, dict] = {}  # token -> session state
        self._seq = 1

    def _next_seq(self) -> int:
        with self._lock:
            self._seq = (self._seq + 1) & 0xFFFFFFFF
            return self._seq

    def _send_packet(self, addr: tuple[str, int], kind: str, seq: int, reliable: int, msg_type: str, payload: dict[str, Any]) -> None:
        if not self.sock:
            return
        packet = {"k": kind, "s": int(seq), "r": int(reliable), "t": msg_type, "p": payload}
        try:
            raw = json.dumps(packet, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            try:
                self.sock.sendto(raw, addr)
                try:
                    print(f"[DEBUG] MatchDaemon.sent -> kind={kind} to={addr} seq={seq} type={msg_type}")
                except Exception:
                    pass
            except Exception as e:
                try:
                    print(f"[DEBUG] MatchDaemon.sendto failed -> addr={addr} kind={kind} seq={seq} err={e}")
                except Exception:
                    pass
        except Exception:
            try:
                print("[DEBUG] MatchDaemon._send_packet: failed to encode/send packet")
            except Exception:
                pass
            return

    def _handle_data(self, addr: tuple[str, int], packet: dict[str, Any]) -> None:
        t = packet.get("t")
        p = packet.get("p") or {}
        if t == "internet_auth":
            token = str(p.get("token") or "").strip()
            player = str(p.get("player") or "").strip()
            if not token or not player:
                # reject
                seq = self._next_seq()
                self._send_packet(addr, PKT_DATA, seq, 0, "internet_auth_error", {"error": "missing token/player"})
                return
            assignment = self.manager.consume_assignment(token)
            if not assignment:
                seq = self._next_seq()
                self._send_packet(addr, PKT_DATA, seq, 0, "internet_auth_error", {"error": "invalid or expired token"})
                return
            # create or join session keyed by assignment.match_id
            match_id = str(assignment.get("match_id"))
            with self._lock:
                session = self._sessions.setdefault(match_id, {
                    "assignment": assignment,
                    "players": {},  # name -> {addr, x,y,last_input}
                    "created_at": time.time(),
                    "round_seq": 0,
                    "start_time": time.time(),
                })
                session_players = session["players"]
                spawn_x = float(PLAYER_START_POS[0]) + 48.0 * float(len(session_players))
                spawn_y = float(PLAYER_START_POS[1])
                session_players[player] = {"addr": addr, "x": spawn_x, "y": spawn_y, "last_input": {}}

            seq = self._next_seq()
            # reply with ok and session id (reuse token as session id)
            self._send_packet(addr, PKT_DATA, seq, 0, "internet_auth_ok", {"session_id": token})
            return

        if t == "input_state":
            # find session by matching addr -> session players
            player = str(p.get("player") or p.get("name") or "")
            if not player:
                return
            with self._lock:
                for session in self._sessions.values():
                    players = session.get("players", {})
                    if player in players:
                        entry = players[player]
                        entry["last_input"] = p.get("input") or {}
                        entry["last_seen"] = time.time()
                        break
            return

        if t == "resync_request":
            player = str(p.get("player") or "")
            with self._lock:
                for session in self._sessions.values():
                    if player in session.get("players", {}):
                        # send immediate snapshot
                        snap = self._build_snapshot(session)
                        seq = self._next_seq()
                        self._send_packet(addr, PKT_DATA, seq, 0, "snapshot", snap)
                        break
            return

    def _handle_hello(self, addr: tuple[str, int]) -> None:
        """Reply to the client's UDP hello so it can complete the session handshake."""
        seq = self._next_seq()
        try:
            print(f"[DEBUG] MatchDaemon._handle_hello -> replying hello_ack to {addr}")
        except Exception:
            pass
        self._send_packet(addr, PKT_HELLO_ACK, seq, 0, "", {})

    def _build_snapshot(self, session: dict) -> dict[str, Any]:
        now = time.time()
        players_list = []
        for name, entry in session.get("players", {}).items():
            players_list.append({
                "player": {
                    "x": float(entry.get("x", 0.0)),
                    "y": float(entry.get("y", 0.0)),
                    "facing": "right",
                    "state": "idle",
                    "falling": False,
                    "drowning": False,
                    "eliminated": False,
                },
                "power": None,
            })
        snapshot = {
            "time_since_start": float(now - session.get("start_time", now)),
            "round_seq": int(session.get("round_seq", 0)),
            "paused": False,
            "game_over": False,
            "target_score": int(session.get("assignment", {}).get("payload", {}).get("target_score", 3)),
            "round_wins": [0 for _ in players_list],
            "match_complete": False,
            "end_state": None,
            "players": players_list,
            "hud": {},
        }
        return snapshot

    def _tick_physics(self, dt: float) -> None:
        with self._lock:
            for session in list(self._sessions.values()):
                players = session.get("players", {})
                for name, entry in players.items():
                    inp = entry.get("last_input") or {}
                    up = bool(inp.get("up"))
                    down = bool(inp.get("down"))
                    left = bool(inp.get("left"))
                    right = bool(inp.get("right"))
                    speed = 160.0
                    dx = 0.0
                    dy = 0.0
                    if left:
                        dx -= speed * dt
                    if right:
                        dx += speed * dt
                    if up:
                        dy -= speed * dt
                    if down:
                        dy += speed * dt
                    entry["x"] = float(entry.get("x", 0.0) + dx)
                    entry["y"] = float(entry.get("y", 0.0) + dy)
                # Keep round_seq stable during a running match.
                # The client uses round_seq as a round-transition marker, so
                # changing it every tick makes the client reset its world state
                # continuously.

    def run(self) -> None:
        self.running = True
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.bind_addr, self.bind_port))
        try:
            print(f"[DEBUG] MatchDaemon.run -> bound to {self.bind_addr}:{self.bind_port}")
        except Exception:
            pass
        s.settimeout(0.05)
        self.sock = s

        last_snapshot_send = 0.0
        last_tick = time.time()
        try:
            while self.running:
                now = time.time()
                dt = now - last_tick
                last_tick = now
                # Tick physics
                self._tick_physics(dt)

                # Send snapshots at 10 Hz
                if now - last_snapshot_send >= 0.1:
                    last_snapshot_send = now
                    with self._lock:
                        for session in list(self._sessions.values()):
                            snap = self._build_snapshot(session)
                            for pname, entry in session.get("players", {}).items():
                                addr = entry.get("addr")
                                if not addr:
                                    continue
                                seq = self._next_seq()
                                self._send_packet(addr, PKT_DATA, seq, 0, "snapshot", snap)

                # Receive incoming datagrams
                try:
                    raw, addr = s.recvfrom(65536)
                except socket.timeout:
                    continue
                except Exception:
                    continue

                try:
                    try:
                        print(f"[DEBUG] MatchDaemon.recv from {addr} raw={raw[:200]!r}")
                    except Exception:
                        pass
                    packet = json.loads(raw.decode("utf-8"))
                    try:
                        print(f"[DEBUG] MatchDaemon.recv decoded -> {packet}")
                    except Exception:
                        pass
                except Exception:
                    try:
                        print("[DEBUG] MatchDaemon: failed to decode incoming UDP datagram")
                    except Exception:
                        pass
                    continue

                if not isinstance(packet, dict):
                    continue
                kind = packet.get("k")
                if kind == PKT_HELLO:
                    self._handle_hello(addr)
                    continue
                if kind == PKT_DATA:
                    self._handle_data(addr, packet)
                elif kind == PKT_FRAGMENT:
                    # ignore fragments in this MVP
                    continue
        finally:
            try:
                s.close()
            except Exception:
                pass
            self.sock = None
            self.running = False


def run_daemon_from_manager(manager: MatchServerManager) -> None:
    # parse manager.bind_endpoint for local bind and manager.endpoint for public advertisement
    endpoint = str(getattr(manager, "bind_endpoint", None) or manager.endpoint or "udp://127.0.0.1:5555")
    host = "0.0.0.0"
    port = 5555
    if "://" in endpoint:
        scheme, rest = endpoint.split("://", 1)
        endpoint = rest
    if "/" in endpoint:
        endpoint = endpoint.split("/", 1)[0]
    if ":" in endpoint:
        try:
            parts = endpoint.rsplit(":", 1)
            host = parts[0] or host
            port = int(parts[1])
        except Exception:
            port = 5555
    md = MatchDaemon(manager, bind_addr=host, bind_port=port)
    md.run()
