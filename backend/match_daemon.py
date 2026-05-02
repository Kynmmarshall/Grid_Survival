from __future__ import annotations

import json
import math
import socket
import threading
import time
from typing import Any

import pygame

from assets import load_tilemap_surface
from collision_manager import CollisionManager
from hazards import HazardManager
from level_config import get_level
from orbs import OrbManager
from backend.vps_match_server import MatchServerManager
from pacman_enemies import PacmanEnemyManager
from network import PKT_DATA, PKT_FRAGMENT, PKT_HELLO, PKT_HELLO_ACK
from settings import MAP_PATH, PLAYER_START_POS, WINDOW_SIZE
from tile_system import TMXTileManager


class _PlayerProxy:
    def __init__(self, name: str, entry: dict[str, Any], *, bot: bool = False):
        self.name = str(name)
        self._entry = entry
        self.position = pygame.Vector2(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
        self.rect = pygame.Rect(0, 0, 48, 48)
        self.rect.center = (round(self.position.x), round(self.position.y))
        self._eliminated = bool(entry.get("eliminated", False))
        self.state = str(entry.get("state", "idle"))
        self.drowning = bool(entry.get("drowning", False))
        self.falling = bool(entry.get("falling", False))
        self._shield_timer = 0.0
        self.bot = bool(bot)
        self._orb_speed_boost = float(entry.get("orb_speed_boost", 1.0))
        self._orb_speed_timer = float(entry.get("orb_speed_timer", 0.0))
        self._shield_timer = float(entry.get("shield_timer", 0.0))
        self._void_walk_timer = float(entry.get("void_walk_timer", 0.0))
        self._freeze_timer = float(entry.get("freeze_timer", 0.0))
        self._power_orb_charges = int(entry.get("power_orb_charges", 0))
        self._lives = int(entry.get("lives", 0))
        self._active_orb_label = str(entry.get("active_orb_label", ""))
        self._active_orb_timer = float(entry.get("active_orb_timer", 0.0))
        # CollisionManager expects player.current_animation.image to exist.
        # On the daemon we only need a simple opaque surface for mask checks.
        dummy_surface = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
        dummy_surface.fill((255, 255, 255, 255))
        self.current_animation = type("_Anim", (), {"image": dummy_surface})()

    def get_feet_rect(self):
        return self.rect

    def has_active_shield(self) -> bool:
        return self._shield_timer > 0.0

    def add_shield(self, duration: float) -> None:
        self._shield_timer = max(self._shield_timer, float(duration))
        self._entry["shield_timer"] = self._shield_timer

    def apply_freeze(self, duration: float) -> None:
        self._freeze_timer = max(self._freeze_timer, float(duration))
        self._entry["freeze_timer"] = self._freeze_timer

    def add_power_orb_charge(self) -> int:
        self._power_orb_charges += 1
        self._entry["power_orb_charges"] = self._power_orb_charges
        return self._power_orb_charges

    def add_life(self) -> None:
        self._lives += 1
        self._entry["lives"] = self._lives

    def enable_void_walk(self, duration: float) -> None:
        self._void_walk_timer = max(self._void_walk_timer, float(duration))
        self._entry["void_walk_timer"] = self._void_walk_timer

    def set_active_orb(self, label: str, duration: float | None) -> None:
        self._active_orb_label = str(label)
        self._active_orb_timer = float(duration or 0.0)
        self._entry["active_orb_label"] = self._active_orb_label
        self._entry["active_orb_timer"] = self._active_orb_timer

    def sync_back(self) -> None:
        self._entry["x"] = float(self.position.x)
        self._entry["y"] = float(self.position.y)
        self._entry["eliminated"] = bool(self._eliminated)
        self._entry["state"] = str(self.state)
        self._entry["falling"] = bool(self.falling)
        self._entry["drowning"] = bool(self.drowning)
        self._entry["bot"] = bool(self.bot)
        self._entry["orb_speed_boost"] = float(self._orb_speed_boost)
        self._entry["orb_speed_timer"] = float(getattr(self, "_orb_speed_timer", 0.0))
        self._entry["shield_timer"] = float(getattr(self, "_shield_timer", 0.0))
        self._entry["void_walk_timer"] = float(getattr(self, "_void_walk_timer", 0.0))
        self._entry["freeze_timer"] = float(getattr(self, "_freeze_timer", 0.0))
        self._entry["power_orb_charges"] = int(getattr(self, "_power_orb_charges", 0))
        self._entry["lives"] = int(getattr(self, "_lives", 0))
        self._entry["active_orb_label"] = str(getattr(self, "_active_orb_label", ""))
        self._entry["active_orb_timer"] = float(getattr(self, "_active_orb_timer", 0.0))


class MatchDaemon:
    """Authoritative UDP match daemon for assigned matches.

    Protocol (UDP JSON envelopes):
    - receives datagrams with JSON packet like {"k":"d","s":seq,"r":0,"t":"internet_auth","p":{...}}
    - responds with same envelope format for PKT_DATA messages.
    - supports messages: internet_auth, input_state, resync_request
    - emits snapshot, world_snapshot periodically.
    """

    CLIENT_TIMEOUT = 30.0  # Stop sending snapshots to clients silent for 30 seconds

    def __init__(self, manager: MatchServerManager, bind_addr: str = "0.0.0.0", bind_port: int | None = None):
        self.manager = manager
        self.bind_addr = bind_addr
        self.bind_port = bind_port or 5555
        self.sock: socket.socket | None = None
        self.running = False
        self.eliminated_players: list[_PlayerProxy] = []
        # RLock avoids deadlock when snapshot send paths call _next_seq()
        # while already inside a lock-protected section.
        self._lock = threading.RLock()
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
                    print(f"[DEBUG] MatchDaemon.sent -> kind={kind} to={addr} seq={seq} type={msg_type}", flush=True)
                except Exception:
                    pass
            except Exception as e:
                try:
                    print(f"[DEBUG] MatchDaemon.sendto failed -> addr={addr} kind={kind} seq={seq} err={e}", flush=True)
                except Exception:
                    pass
        except Exception:
            try:
                print("[DEBUG] MatchDaemon._send_packet: failed to encode/send packet", flush=True)
            except Exception:
                pass
            return

    @staticmethod
    def _looks_like_hello_probe(raw: bytes) -> bool:
        """Best-effort hello detection for malformed/partial JSON probes."""
        if not raw:
            return False
        if raw in {b"h", b"hello", b"HELLO"}:
            return True
        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            return False
        compact = text.replace(" ", "")
        return '"k":"h"' in compact

    def _handle_data(self, addr: tuple[str, int], packet: dict[str, Any]) -> None:
        t = packet.get("t")
        p = packet.get("p") or {}

        def touch_addr() -> None:
            now = time.time()
            with self._lock:
                for session in self._sessions.values():
                    for entry in session.get("players", {}).values():
                        if entry.get("addr") == addr:
                            entry["last_seen"] = now
                            return

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
                is_new_session = match_id not in self._sessions
                session = self._sessions.setdefault(match_id, {
                    "assignment": assignment,
                    "players": {},  # name -> {addr, x,y,last_input}
                    "bot_names": [],
                    "bot_profiles": {},
                    "enemy_manager": None,
                    "bot_ai_timer": 0.0,
                    "created_at": time.time(),
                    "round_seq": 0,
                    "start_time": time.time(),
                })
                session_players = session["players"]
                spawn_x = float(PLAYER_START_POS[0]) + 48.0 * float(len(session_players))
                spawn_y = float(PLAYER_START_POS[1])
                session_players[player] = {"addr": addr, "x": spawn_x, "y": spawn_y, "last_input": {}, "last_seen": time.time()}
                bot_entries = assignment.get("payload", {}).get("players", [])
                if isinstance(bot_entries, list) and not session.get("bot_names"):
                    for idx, entry in enumerate(bot_entries):
                        if not isinstance(entry, dict) or not bool(entry.get("bot", False)):
                            continue
                        bot_name = str(entry.get("name", f"BOT-{idx + 1}"))
                        session["bot_names"].append(bot_name)
                        session["bot_profiles"][bot_name] = str(entry.get("profile", "Bot"))
                        bot_x = float(PLAYER_START_POS[0]) + 56.0 * float(len(session_players) + len(session["bot_names"]))
                        bot_y = float(PLAYER_START_POS[1])
                        session_players[bot_name] = {
                            "addr": None,
                            "x": bot_x,
                            "y": bot_y,
                            "last_input": {},
                            "bot": True,
                            "profile": str(entry.get("profile", "Bot")),
                        }
                    if session.get("bot_names"):
                        enemy_spawns = self._build_enemy_spawns(session)
                        session["enemy_manager"] = PacmanEnemyManager(enemy_spawns)
                self._initialize_session_world(session)

            seq = self._next_seq()
            # reply with ok and session id (reuse token as session id)
            self._send_packet(addr, PKT_DATA, seq, 0, "internet_auth_ok", {"session_id": token})
            try:
                if is_new_session:
                    print(f"[SESSION] New session created: match_id={match_id}, player={player}, addr={addr}", flush=True)
                else:
                    print(f"[SESSION] Player joined existing session: match_id={match_id}, player={player}, addr={addr}, active_players={len([p for p in session_players.values() if p.get('addr')])}", flush=True)
            except Exception:
                pass
            return

        if t == "input_state":
            # Refresh liveness from the packet source address.
            touch_addr()
            with self._lock:
                for session in self._sessions.values():
                    for entry in session.get("players", {}).values():
                        if entry.get("addr") != addr:
                            continue
                        entry["last_input"] = p.get("input") or {}
                        break
            return

        if t == "resync_request":
            touch_addr()
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
            print(f"[DEBUG] MatchDaemon._handle_hello -> replying hello_ack to {addr}", flush=True)
        except Exception:
            pass
        self._send_packet(addr, PKT_HELLO_ACK, seq, 0, "", {})

        # Track hello reception for client timeout detection
        with self._lock:
            for session in self._sessions.values():
                players = session.get("players", {})
                for entry in players.values():
                    if entry.get("addr") == addr:
                        entry["last_seen"] = time.time()

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
                    "eliminated": bool(entry.get("eliminated", False)),
                },
                "power": None,
                "bot": bool(entry.get("bot", False)),
                "name": name,
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

    def _build_enemy_spawns(self, session: dict) -> list[tuple[int, int]]:
        players = session.get("players", {})
        if players:
            positions = [
                (int(round(entry.get("x", PLAYER_START_POS[0]))), int(round(entry.get("y", PLAYER_START_POS[1]))))
                for entry in players.values()
            ]
        else:
            positions = [PLAYER_START_POS]

        base_x = int(WINDOW_SIZE[0] * 0.5)
        base_y = int(WINDOW_SIZE[1] * 0.42)
        offsets = [
            (0, -140),
            (140, 0),
            (0, 140),
            (-140, 0),
        ]
        spawns: list[tuple[int, int]] = []
        for idx, offset in enumerate(offsets):
            if len(spawns) >= max(1, len(session.get("bot_names", []))):
                break
            spawns.append((base_x + offset[0], base_y + offset[1]))
        while len(spawns) < max(1, len(session.get("bot_names", []))):
            px, py = positions[len(spawns) % len(positions)]
            spawns.append((px + 120 + len(spawns) * 30, py - 80))
        return spawns

    def _initialize_session_world(self, session: dict) -> None:
        if session.get("world_initialized"):
            return

        payload = session.get("assignment", {}).get("payload", {})
        map_id = int(payload.get("map_id", 1) or 1)
        level = get_level(map_id)

        _, tmx_data, walkable_mask, walkable_bounds, scale_x, scale_y, map_offset = load_tilemap_surface(WINDOW_SIZE, MAP_PATH)
        tile_manager = None
        if tmx_data is not None:
            tile_manager = TMXTileManager(tmx_data, scale_x, scale_y, map_offset)
            tile_manager.grace_period = float(level.tile.grace_period)
            tile_manager.base_disappear_interval = float(level.tile.base_interval)
            tile_manager.min_disappear_interval = float(level.tile.min_interval)
            tile_manager.difficulty_scale_rate = float(level.tile.scale_rate)
            tile_manager.current_interval = float(level.tile.base_interval)
            tile_manager.simultaneous_tiles = int(level.tile.base_simultaneous)
            tile_manager.time_elapsed = 0.0
            tile_manager.grace_timer = 0.0
            tile_manager.disappear_timer = 0.0

        collision_manager = CollisionManager()
        hazard_manager = HazardManager(collision_manager)
        hazard_manager.hazard_start_time = float(level.hazard.start_delay)
        hazard_manager.bullet_spawn_interval = float(level.hazard.bullet_interval)
        hazard_manager.min_bullet_interval = float(level.hazard.bullet_min_interval)
        hazard_manager.trap_spawn_interval = float(level.hazard.trap_interval)
        hazard_manager.min_trap_interval = float(level.hazard.trap_min_interval)
        hazard_manager.difficulty_scale_rate = float(level.hazard.difficulty_scale_rate)
        hazard_manager.bullet_spawn_timer = 0.0
        hazard_manager.trap_spawn_timer = 0.0
        hazard_manager.time_elapsed = 0.0

        orb_manager = OrbManager(level.number)

        session["level"] = level
        session["tile_manager"] = tile_manager
        session["collision_manager"] = collision_manager
        session["hazard_manager"] = hazard_manager
        session["orb_manager"] = orb_manager
        session["walkable_mask"] = walkable_mask
        session["walkable_bounds"] = walkable_bounds
        session["world_initialized"] = True

    def _build_world_snapshot(self, session: dict) -> dict[str, Any]:
        tile_manager = session.get("tile_manager")
        return {
            "time_since_start": float(time.time() - session.get("start_time", time.time())),
            "round_seq": int(session.get("round_seq", 0)),
            "tiles": tile_manager.snapshot_state() if tile_manager is not None else None,
        }

    def _build_world_dynamic_snapshot(self, session: dict) -> dict[str, Any]:
        hazard_manager = session.get("hazard_manager")
        orb_manager = session.get("orb_manager")
        enemy_manager = session.get("enemy_manager")
        return {
            "time_since_start": float(time.time() - session.get("start_time", time.time())),
            "round_seq": int(session.get("round_seq", 0)),
            "hazards": hazard_manager.snapshot_state() if hazard_manager is not None else None,
            "orbs": orb_manager.snapshot_state() if orb_manager is not None else None,
            "pacman_enemies": enemy_manager.snapshot_state() if enemy_manager is not None else None,
        }

    def _rescue_player_to_safe_tile(self, player: Any) -> bool:
        try:
            if hasattr(player, "_eliminated"):
                player._eliminated = False
            if hasattr(player, "state"):
                player.state = "idle"
            if hasattr(player, "position"):
                player.position.x = float(PLAYER_START_POS[0])
                player.position.y = float(PLAYER_START_POS[1])
            if hasattr(player, "rect"):
                player.rect.center = (int(PLAYER_START_POS[0]), int(PLAYER_START_POS[1]))
            if hasattr(player, "sync_back"):
                player.sync_back()
            return True
        except Exception:
            return False

    def _tick_bots(self, session: dict, dt: float) -> None:
        bot_names = list(session.get("bot_names", []))
        if not bot_names:
            return

        players = session.get("players", {})
        humans = [name for name, entry in players.items() if not bool(entry.get("bot", False)) and not bool(entry.get("eliminated", False))]
        if not humans:
            return

        session["bot_ai_timer"] = float(session.get("bot_ai_timer", 0.0) + dt)
        choose_new_input = session["bot_ai_timer"] >= 0.18
        if choose_new_input:
            session["bot_ai_timer"] = 0.0

        for bot_name in bot_names:
            entry = players.get(bot_name)
            if not entry or bool(entry.get("eliminated", False)):
                continue
            if not choose_new_input and entry.get("last_input"):
                continue

            bot_pos = pygame.Vector2(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
            nearest_human = None
            nearest_dist = float("inf")
            for human_name in humans:
                human_entry = players.get(human_name)
                if not human_entry:
                    continue
                human_pos = pygame.Vector2(float(human_entry.get("x", 0.0)), float(human_entry.get("y", 0.0)))
                dist = bot_pos.distance_to(human_pos)
                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_human = human_pos

            if nearest_human is None:
                continue

            delta = nearest_human - bot_pos
            move = {"up": False, "down": False, "left": False, "right": False}
            if abs(delta.x) > 8.0:
                move["right"] = delta.x > 0
                move["left"] = delta.x < 0
            if abs(delta.y) > 8.0:
                move["down"] = delta.y > 0
                move["up"] = delta.y < 0

            # Nudge bots to keep moving even when already near the target.
            if not any(move.values()):
                move["right"] = True

            entry["last_input"] = move

    def _tick_physics(self, dt: float) -> None:
        with self._lock:
            for session in list(self._sessions.values()):
                players = session.get("players", {})
                self._initialize_session_world(session)
                self._tick_bots(session, dt)
                player_proxies: dict[str, _PlayerProxy] = {
                    name: _PlayerProxy(name, entry, bot=bool(entry.get("bot", False)))
                    for name, entry in players.items()
                }
                for name, entry in players.items():
                    proxy = player_proxies.get(name)
                    if proxy is None or bool(entry.get("eliminated", False)):
                        continue
                    proxy._orb_speed_timer = max(0.0, float(entry.get("orb_speed_timer", 0.0) or 0.0) - dt)
                    proxy._shield_timer = max(0.0, float(entry.get("shield_timer", 0.0) or 0.0) - dt)
                    proxy._void_walk_timer = max(0.0, float(entry.get("void_walk_timer", 0.0) or 0.0) - dt)
                    proxy._freeze_timer = max(0.0, float(entry.get("freeze_timer", 0.0) or 0.0) - dt)
                    if proxy._orb_speed_timer <= 0.0:
                        proxy._orb_speed_boost = 1.0
                    else:
                        proxy._orb_speed_boost = max(1.0, float(entry.get("orb_speed_boost", 1.0) or 1.0))
                    inp = entry.get("last_input") or {}
                    up = bool(inp.get("up"))
                    down = bool(inp.get("down"))
                    left = bool(inp.get("left"))
                    right = bool(inp.get("right"))
                    speed = 160.0 * float(proxy._orb_speed_boost or 1.0)
                    if proxy._freeze_timer > 0.0:
                        speed *= 0.2
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

                    proxy.position.x = float(entry.get("x", 0.0) + dx)
                    proxy.position.y = float(entry.get("y", 0.0) + dy)
                    proxy.rect.center = (round(proxy.position.x), round(proxy.position.y))
                    proxy.sync_back()

                tile_manager = session.get("tile_manager")
                if tile_manager is not None:
                    tile_manager.update(dt)
                    original_mask = session.get("walkable_mask")
                    if original_mask is not None:
                        session["walkable_mask"] = tile_manager.get_updated_walkable_mask(original_mask)

                hazard_manager = session.get("hazard_manager")
                if hazard_manager is not None:
                    hazard_manager.update(dt)

                enemy_manager = session.get("enemy_manager")
                if enemy_manager is None and session.get("bot_names"):
                    enemy_manager = PacmanEnemyManager(self._build_enemy_spawns(session))
                    session["enemy_manager"] = enemy_manager

                current_proxies = list(player_proxies.values())
                self.eliminated_players = [proxy for proxy in current_proxies if proxy._eliminated]

                if hazard_manager is not None:
                    for proxy in current_proxies:
                        if proxy._eliminated:
                            continue
                        if hazard_manager.check_player_collision(proxy):
                            proxy._eliminated = True
                            proxy.state = "death"
                            self.eliminated_players.append(proxy)

                if enemy_manager is not None:
                    victims = enemy_manager.update(
                        dt,
                        current_proxies,
                        session.get("walkable_mask"),
                        session.get("walkable_bounds") or pygame.Rect(0, 0, WINDOW_SIZE[0], WINDOW_SIZE[1]),
                    )
                    for victim in victims:
                        victim_name = getattr(victim, "name", None)
                        proxy = player_proxies.get(str(victim_name))
                        if proxy is not None:
                            proxy._eliminated = True
                            proxy.state = "death"
                            if proxy not in self.eliminated_players:
                                self.eliminated_players.append(proxy)

                orb_manager = session.get("orb_manager")
                if orb_manager is not None:
                    orb_manager.update(dt, session.get("walkable_bounds"), current_proxies, self)

                for proxy in current_proxies:
                    proxy.sync_back()

                # Keep round_seq stable during a running match.
                # The client uses round_seq as a round-transition marker, so
                # changing it every tick makes the client reset its world state
                # continuously.

    def _cleanup_stale_sessions(self, now: float) -> None:
        """Remove sessions with no active players for >90 seconds."""
        stale_sessions = []
        with self._lock:
            for session_id, session in list(self._sessions.items()):
                # Check if session has any non-stale players
                has_active_player = False
                for pname, entry in session.get("players", {}).items():
                    last_seen = entry.get("last_seen", now)
                    if now - last_seen <= self.CLIENT_TIMEOUT:
                        has_active_player = True
                        break
                
                # Session is stale if created >90s ago AND no active players
                created_at = session.get("created_at", now)
                session_age = now - created_at
                if session_age > 90.0 and not has_active_player:
                    stale_sessions.append(session_id)
            
            # Remove stale sessions
            for session_id in stale_sessions:
                session = self._sessions.pop(session_id, None)
                if session:
                    try:
                        print(f"[CLEANUP] Removed stale session {session_id} (age={now - session.get('created_at', now):.1f}s, players={len(session.get('players', {}))})", flush=True)
                    except Exception:
                        pass

    def run(self) -> None:
        self.running = True
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((self.bind_addr, self.bind_port))
        try:
            print(f"[DEBUG] MatchDaemon.run -> bound to {self.bind_addr}:{self.bind_port}", flush=True)
        except Exception:
            pass
        s.settimeout(0.05)
        self.sock = s

        last_snapshot_send = 0.0
        last_cleanup = 0.0
        last_tick = time.time()
        try:
            while self.running:
                now = time.time()
                dt = now - last_tick
                last_tick = now
                # Tick physics
                self._tick_physics(dt)

                # Cleanup stale sessions every 10 seconds
                if now - last_cleanup >= 10.0:
                    last_cleanup = now
                    self._cleanup_stale_sessions(now)

                # Send snapshots at 10 Hz
                if now - last_snapshot_send >= 0.1:
                    last_snapshot_send = now
                    with self._lock:
                        for session in list(self._sessions.values()):
                            snap = self._build_snapshot(session)
                            world_snapshot = self._build_world_snapshot(session)
                            dynamic_snapshot = self._build_world_dynamic_snapshot(session)
                            for pname, entry in session.get("players", {}).items():
                                addr = entry.get("addr")
                                if not addr:
                                    continue

                                # Skip sending snapshots to stale clients (no activity for >CLIENT_TIMEOUT)
                                last_seen = entry.get("last_seen", now)
                                if now - last_seen > self.CLIENT_TIMEOUT:
                                    try:
                                        print(f"[DEBUG] MatchDaemon: skipping stale client {addr} (last_seen {now - last_seen:.1f}s ago)", flush=True)
                                    except Exception:
                                        pass
                                    continue

                                seq = self._next_seq()
                                self._send_packet(addr, PKT_DATA, seq, 0, "snapshot", snap)
                                seq = self._next_seq()
                                self._send_packet(addr, PKT_DATA, seq, 0, "world_snapshot", world_snapshot)
                                if dynamic_snapshot is not None:
                                    seq = self._next_seq()
                                    self._send_packet(addr, PKT_DATA, seq, 0, "world_dynamic_snapshot", dynamic_snapshot)

                # Receive incoming datagrams
                try:
                    raw, addr = s.recvfrom(65536)
                except socket.timeout:
                    continue
                except Exception:
                    continue

                try:
                    try:
                        print(f"[DEBUG] MatchDaemon.recv from {addr} raw={raw[:200]!r}", flush=True)
                    except Exception:
                        pass
                    packet = json.loads(raw.decode("utf-8"))
                    try:
                        print(f"[DEBUG] MatchDaemon.recv decoded -> {packet}", flush=True)
                    except Exception:
                        pass
                except Exception:
                    # Some clients/middleboxes may alter probe payload formatting;
                    # still answer hello probes to establish UDP reachability.
                    if self._looks_like_hello_probe(raw):
                        self._handle_hello(addr)
                        continue
                    try:
                        print("[DEBUG] MatchDaemon: failed to decode incoming UDP datagram", flush=True)
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
