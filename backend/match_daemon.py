from __future__ import annotations

import base64
import json
import math
import random
import socket
import threading
import time
from typing import Any

import os
# On headless servers force SDL to use the dummy audio driver to avoid ALSA errors
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame

from assets import load_tilemap_surface
from collision_manager import CollisionManager
from hazards import HazardManager
from level_config import get_level
from orbs import OrbManager
from backend.vps_match_server import MatchServerManager
from backend.vps_sync_server import DB_PATH as VPS_ACCOUNT_DB_PATH, RemoteAccountStore
from pacman_enemies import PacmanEnemyManager
from network import (
    FRAGMENT_RAW_CHUNK_BYTES,
    MAX_MESSAGE_BYTES,
    MAX_UDP_DATAGRAM_BYTES,
    PKT_DATA,
    PKT_DISCONNECT,
    PKT_FRAGMENT,
    PKT_HELLO,
    PKT_HELLO_ACK,
)
from settings import (
    MAP_PATH,
    PLAYER_FALL_GRAVITY,
    PLAYER_FALL_MAX_SPEED,
    PLAYER_SPEED,
    PLAYER_START_POS,
    WINDOW_SIZE,
)

from projectiles import ProjectileManager

QUEUE_FILL_TIMEOUT = 12.0  # seconds to wait in queue before filling with bots
from tile_system import TMXTileManager, TileState


ONLINE_TILE_GRACE_PERIOD = 5.0
ONLINE_TILE_BASE_INTERVAL = 4.0
ONLINE_TILE_MIN_INTERVAL = 1.5
ONLINE_TILE_SCALE_RATE = 0.97
ONLINE_INITIAL_TILE_BURST = 1
ONLINE_PACMAN_ENEMY_COUNT = 2
ROUND_RESTART_DELAY = 2.0
MAX_TICK_DT = 0.1
ONLINE_HAZARD_START_DELAY_BONUS = 6.0
ONLINE_HAZARD_INTERVAL_MULTIPLIER = 1.45
ONLINE_HAZARD_SCALE_RATE = 0.992
ONLINE_HAZARD_MIN_BULLET_INTERVAL = 1.5
ONLINE_HAZARD_MIN_TRAP_INTERVAL = 6.5

BOT_ROAM_RETARGET_SECONDS = 2.8
BOT_LOOKAHEAD_DISTANCE = 54.0
BOT_THREAT_RADIUS = 240.0
BOT_SPREAD_RADIUS = 180.0
BOT_EDGE_SAMPLE_OFFSETS = (
    pygame.Vector2(0, 28),
    pygame.Vector2(0, -28),
    pygame.Vector2(28, 0),
    pygame.Vector2(-28, 0),
    pygame.Vector2(22, 22),
    pygame.Vector2(-22, 22),
    pygame.Vector2(22, -22),
    pygame.Vector2(-22, -22),
)

BOT_CANDIDATE_DIRECTIONS = (
    pygame.Vector2(0, 0),
    pygame.Vector2(1, 0),
    pygame.Vector2(-1, 0),
    pygame.Vector2(0, 1),
    pygame.Vector2(0, -1),
    pygame.Vector2(1, 1).normalize(),
    pygame.Vector2(-1, 1).normalize(),
    pygame.Vector2(1, -1).normalize(),
    pygame.Vector2(-1, -1).normalize(),
)


class _PlayerProxy:
    def __init__(self, name: str, entry: dict[str, Any], *, bot: bool = False):
        self.name = str(name)
        self._entry = entry
        self.position = pygame.Vector2(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
        self.rect = pygame.Rect(0, 0, 48, 48)
        self.rect.center = (round(self.position.x), round(self.position.y))
        self._eliminated = bool(entry.get("eliminated", False))
        self.state = str(entry.get("state", "idle"))
        self.facing = str(entry.get("facing", "down"))
        self.velocity = pygame.Vector2(
            float(entry.get("velocity_x", 0.0)),
            float(entry.get("velocity_y", 0.0)),
        )
        self.drowning = bool(entry.get("drowning", False))
        self.falling = bool(entry.get("falling", False))
        self.fall_velocity = float(entry.get("fall_velocity", 0.0))
        self.jumping = bool(entry.get("jumping", False))
        self.z = float(entry.get("z", 0.0))
        self.z_velocity = float(entry.get("z_velocity", 0.0))
        self.on_ground = bool(entry.get("on_ground", True))
        self._shield_timer = 0.0
        self.bot = bool(bot)
        self._orb_speed_boost = float(entry.get("orb_speed_boost", 1.0))
        self._orb_speed_timer = float(entry.get("orb_speed_timer", 0.0))
        self._shield_timer = float(entry.get("shield_timer", 0.0))
        self._void_walk_timer = float(entry.get("void_walk_timer", 0.0))
        self._freeze_timer = float(entry.get("freeze_timer", 0.0))
        self._power_orb_charges = int(entry.get("power_orb_charges", 0))
        self._lives = int(entry.get("extra_lives", entry.get("lives", 0)))
        self._active_orb_label = str(entry.get("active_orb_label", ""))
        self._active_orb_timer = float(entry.get("active_orb_timer", 0.0))
        self._death_fade_alpha = int(entry.get("death_fade_alpha", 255))
        self._feet_mask = None
        self._feet_mask_count = 0
        # CollisionManager expects player.current_animation.image to exist.
        # On the daemon we only need a simple opaque surface for mask checks.
        dummy_surface = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
        dummy_surface.fill((255, 255, 255, 255))
        self.current_animation = type("_Anim", (), {"image": dummy_surface, "finished": True})()

    def get_feet_rect(self):
        width = max(4, int(self.rect.width * 0.03))
        height = max(4, int(self.rect.height * 0.03))
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (
            round(self.position.x),
            round(self.position.y + self.rect.height * 0.25),
        )
        return rect

    def get_hitbox(self) -> pygame.Rect:
        return self.rect.inflate(-int(self.rect.width * 0.4), -int(self.rect.height * 0.4))

    def has_active_shield(self) -> bool:
        return self._shield_timer > 0.0

    def has_void_walk(self) -> bool:
        return self._void_walk_timer > 0.0

    def has_extra_life(self) -> bool:
        return self._lives > 0

    def use_life(self) -> bool:
        if self._lives <= 0:
            return False
        self._lives -= 1
        self._entry["extra_lives"] = self._lives
        return True

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
        self._entry["extra_lives"] = self._lives

    def enable_void_walk(self, duration: float) -> None:
        self._void_walk_timer = max(self._void_walk_timer, float(duration))
        self._entry["void_walk_timer"] = self._void_walk_timer

    def set_active_orb(self, label: str, duration: float | None) -> None:
        self._active_orb_label = str(label)
        self._active_orb_timer = float(duration or 0.0)
        self._entry["active_orb_label"] = self._active_orb_label
        self._entry["active_orb_timer"] = self._active_orb_timer

    def _feet_mask_for_rect(self, rect: pygame.Rect) -> pygame.mask.Mask:
        size = rect.size
        if self._feet_mask is None or self._feet_mask.get_size() != size:
            self._feet_mask = pygame.mask.Mask(size)
            self._feet_mask.fill()
            self._feet_mask_count = self._feet_mask.count()
        return self._feet_mask

    def is_over_platform(self, position: pygame.Vector2, walkable_mask) -> bool:
        if self.has_void_walk():
            return True
        if walkable_mask is None:
            return True
        feet_rect = self.get_feet_rect().copy()
        feet_rect.center = (
            round(position.x),
            round(position.y + self.rect.height * 0.25),
        )
        feet_mask = self._feet_mask_for_rect(feet_rect)
        return walkable_mask.overlap_area(feet_mask, feet_rect.topleft) == self._feet_mask_count

    def attempt_move(self, delta: pygame.Vector2, walkable_mask) -> bool:
        proposed = self.position + delta
        if self.is_over_platform(proposed, walkable_mask):
            self.position = proposed
            return True

        if delta.x:
            proposed_x = pygame.Vector2(self.position.x + delta.x, self.position.y)
            if self.is_over_platform(proposed_x, walkable_mask):
                self.position.x = proposed_x.x
                return True

        if delta.y:
            proposed_y = pygame.Vector2(self.position.x, self.position.y + delta.y)
            if self.is_over_platform(proposed_y, walkable_mask):
                self.position.y = proposed_y.y
                return True

        self.position = proposed
        return False

    def start_fall(self) -> None:
        if self.falling or self.state == "death":
            return
        self.falling = True
        self.on_ground = False
        self.fall_velocity = 0.0
        self.velocity.update(0, 0)

    def update_fall(self, dt: float) -> None:
        self.fall_velocity = min(
            self.fall_velocity + PLAYER_FALL_GRAVITY * dt,
            PLAYER_FALL_MAX_SPEED,
        )
        self.position.y += self.fall_velocity * dt
        self.velocity.update(0.0, self.fall_velocity)

    def die(self) -> None:
        if self.state == "death":
            return
        self.state = "death"
        self.falling = False
        self.drowning = False
        self.jumping = False
        self.velocity.update(0, 0)
        self._death_fade_alpha = 255

    def update_death(self, dt: float) -> None:
        self._death_fade_alpha = max(0, int(self._death_fade_alpha - 220 * dt))

    def sync_back(self) -> None:
        self._entry["x"] = float(self.position.x)
        self._entry["y"] = float(self.position.y)
        self._entry["eliminated"] = bool(self._eliminated)
        self._entry["state"] = str(self.state)
        self._entry["facing"] = str(self.facing)
        self._entry["falling"] = bool(self.falling)
        self._entry["fall_velocity"] = float(self.fall_velocity)
        self._entry["drowning"] = bool(self.drowning)
        self._entry["jumping"] = bool(self.jumping)
        self._entry["z"] = float(self.z)
        self._entry["z_velocity"] = float(self.z_velocity)
        self._entry["on_ground"] = bool(self.on_ground)
        self._entry["velocity_x"] = float(self.velocity.x)
        self._entry["velocity_y"] = float(self.velocity.y)
        self._entry["bot"] = bool(self.bot)
        self._entry["orb_speed_boost"] = float(self._orb_speed_boost)
        self._entry["orb_speed_timer"] = float(getattr(self, "_orb_speed_timer", 0.0))
        self._entry["shield_timer"] = float(getattr(self, "_shield_timer", 0.0))
        self._entry["void_walk_timer"] = float(getattr(self, "_void_walk_timer", 0.0))
        self._entry["freeze_timer"] = float(getattr(self, "_freeze_timer", 0.0))
        self._entry["power_orb_charges"] = int(getattr(self, "_power_orb_charges", 0))
        self._entry["extra_lives"] = int(getattr(self, "_lives", 0))
        self._entry["active_orb_label"] = str(getattr(self, "_active_orb_label", ""))
        self._entry["active_orb_timer"] = float(getattr(self, "_active_orb_timer", 0.0))
        self._entry["death_fade_alpha"] = int(getattr(self, "_death_fade_alpha", 255))


class MatchDaemon:
    """Authoritative UDP match daemon for assigned matches.

    Now supports hybrid TCP+UDP:
    - TCP (port 5554): Handshake & authentication (hello, hello_ack, internet_auth, internet_auth_ok)
    - UDP (port 5555): Game state snapshots and player input (faster, stateless)
    """

    CLIENT_TIMEOUT = 30.0  # Stop sending snapshots to clients silent for 30 seconds

    def __init__(self, manager: MatchServerManager, bind_addr: str = "0.0.0.0", bind_port: int | None = None, tcp_port: int | None = None):
        self.manager = manager
        self.bind_addr = bind_addr
        self.bind_port = bind_port or 5555
        self.tcp_port = tcp_port or 5554  # TCP on port one before UDP
        self.sock: socket.socket | None = None
        self.tcp_sock: socket.socket | None = None
        self.running = False
        self.eliminated_players: list[_PlayerProxy] = []
        self.account_store = None
        try:
            self.account_store = RemoteAccountStore(VPS_ACCOUNT_DB_PATH)
        except Exception as exc:
            try:
                print(f"[ACCOUNT] Failed to open VPS account store: {exc}", flush=True)
            except Exception:
                pass
        # RLock avoids deadlock when snapshot send paths call _next_seq()
        # while already inside a lock-protected section.
        self._lock = threading.RLock()
        self._sessions: dict[str, dict] = {}  # token -> session state
        self._seq = 1
        self._tcp_addr_to_session: dict[tuple[str, int], str] = {}  # Maps TCP peer addr to session token

    def _next_seq(self) -> int:
        with self._lock:
            self._seq = (self._seq + 1) & 0xFFFFFFFF
            return self._seq

    def _encode_packet_datagrams(
        self,
        *,
        kind: str,
        seq: int,
        reliable: int,
        msg_type: str,
        payload: dict[str, Any],
    ) -> tuple[list[bytes], int]:
        packet = {"k": kind, "s": int(seq), "r": int(reliable), "t": msg_type, "p": payload}
        raw = json.dumps(packet, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        raw_size = len(raw)
        if raw_size > MAX_MESSAGE_BYTES:
            raise ValueError(f"packet too large: {raw_size} bytes")
        if raw_size <= MAX_UDP_DATAGRAM_BYTES:
            return [raw], raw_size

        datagrams: list[bytes] = []
        total = (raw_size + FRAGMENT_RAW_CHUNK_BYTES - 1) // FRAGMENT_RAW_CHUNK_BYTES
        for idx in range(total):
            start = idx * FRAGMENT_RAW_CHUNK_BYTES
            end = min(raw_size, start + FRAGMENT_RAW_CHUNK_BYTES)
            frag = {
                "k": PKT_FRAGMENT,
                "s": int(seq),
                "r": int(reliable),
                "i": int(idx),
                "n": int(total),
                "x": base64.b64encode(raw[start:end]).decode("ascii"),
            }
            frag_raw = json.dumps(frag, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
            if len(frag_raw) > MAX_UDP_DATAGRAM_BYTES:
                raise ValueError(f"fragment too large: {len(frag_raw)} bytes")
            datagrams.append(frag_raw)
        return datagrams, raw_size

    def _send_packet(self, addr: tuple[str, int], kind: str, seq: int, reliable: int, msg_type: str, payload: dict[str, Any]) -> None:
        if not self.sock:
            return
        try:
            datagrams, raw_size = self._encode_packet_datagrams(
                kind=kind,
                seq=seq,
                reliable=reliable,
                msg_type=msg_type,
                payload=payload,
            )
            for datagram in datagrams:
                self.sock.sendto(datagram, addr)
            if kind == "ha" or msg_type in {"internet_auth_ok", "snapshot"}:
                try:
                    print(
                        f"[SEND] {kind}/{msg_type} -> {addr} "
                        f"(seq={seq}, reliable={reliable}, size={raw_size}, packets={len(datagrams)})",
                        flush=True,
                    )
                except Exception:
                    pass
        except Exception as e:
            try:
                print(f"[SEND_ERROR] Failed to send {kind}/{msg_type} to {addr}: {e}", flush=True)
            except Exception:
                pass
            return

    def _expected_player_count(self, session: dict) -> int:
        players = session.get("assignment", {}).get("payload", {}).get("players", [])
        if isinstance(players, list) and players:
            return len(players)
        return max(2, len(session.get("players", {})))

    def _session_ready(self, session: dict) -> bool:
        assigned_players = session.get("assignment", {}).get("payload", {}).get("players", [])
        if not isinstance(assigned_players, list) or not assigned_players:
            return bool(session.get("players"))

        expected_humans = sum(
            1
            for player in assigned_players
            if isinstance(player, dict) and not bool(player.get("bot", False))
        )
        registered_humans = sum(
            1
            for entry in session.get("players", {}).values()
            if not bool(entry.get("bot", False))
        )
        return registered_humans >= max(1, expected_humans)

    def _ensure_round_wins(self, session: dict) -> list[int]:
        total = max(self._expected_player_count(session), len(session.get("players", {})))
        raw_wins = session.get("round_wins")
        if isinstance(raw_wins, list):
            wins = [int(max(0, value)) for value in raw_wins[:total]]
        else:
            wins = []
        if len(wins) < total:
            wins.extend([0] * (total - len(wins)))
        session["round_wins"] = wins
        return wins

    @staticmethod
    def _player_entry_snapshot(entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "x": float(entry.get("x", 0.0)),
            "y": float(entry.get("y", 0.0)),
            "facing": str(entry.get("facing", "down")),
            "state": str(entry.get("state", "death" if entry.get("eliminated") else "idle")),
            "falling": bool(entry.get("falling", False)),
            "fall_velocity": float(entry.get("fall_velocity", 0.0)),
            "drowning": bool(entry.get("drowning", False)),
            "jumping": bool(entry.get("jumping", False)),
            "z": float(entry.get("z", 0.0)),
            "z_velocity": float(entry.get("z_velocity", 0.0)),
            "on_ground": bool(entry.get("on_ground", True)),
            "velocity_x": float(entry.get("velocity_x", 0.0)),
            "velocity_y": float(entry.get("velocity_y", 0.0)),
            "character_name": str(entry.get("character_name", "Caveman")),
            "power_orb_charges": int(entry.get("power_orb_charges", 0)),
            "shield_timer": float(entry.get("shield_timer", 0.0)),
            "freeze_timer": float(entry.get("freeze_timer", 0.0)),
            "power_alpha": 255,
            "power_speed_boost": float(entry.get("power_speed_boost", 1.0)),
            "power_jump_boost": float(entry.get("power_jump_boost", 1.0)),
            "orb_speed_boost": float(entry.get("orb_speed_boost", 1.0)),
            "active_orb_label": entry.get("active_orb_label", ""),
            "active_orb_timer": float(entry.get("active_orb_timer", 0.0)),
            "active_orb_indefinite": bool(entry.get("active_orb_indefinite", False)),
            "active_orb_duration": float(entry.get("active_orb_duration", 0.0)),
            "eliminated": bool(entry.get("eliminated", False)),
            "extra_lives": int(entry.get("extra_lives", 0)),
            "death_fade_alpha": int(entry.get("death_fade_alpha", 255)),
        }

    def _configure_tile_manager(self, tile_manager: TMXTileManager, level) -> None:
        tile_manager.grace_period = max(ONLINE_TILE_GRACE_PERIOD, float(level.tile.grace_period))
        tile_manager.base_disappear_interval = max(
            ONLINE_TILE_BASE_INTERVAL,
            float(level.tile.base_interval),
        )
        tile_manager.min_disappear_interval = max(
            ONLINE_TILE_MIN_INTERVAL,
            float(level.tile.min_interval),
        )
        tile_manager.difficulty_scale_rate = max(
            ONLINE_TILE_SCALE_RATE,
            float(level.tile.scale_rate),
        )
        tile_manager.current_interval = float(tile_manager.base_disappear_interval)
        tile_manager.simultaneous_tiles = min(
            ONLINE_INITIAL_TILE_BURST,
            max(1, int(level.tile.base_simultaneous)),
        )
        tile_manager.time_elapsed = 0.0
        tile_manager.grace_timer = 0.0
        tile_manager.disappear_timer = 0.0

    def _configure_hazard_manager(self, hazard_manager: HazardManager, level) -> None:
        hazard_manager.hazard_start_time = max(
            float(level.hazard.start_delay),
            float(level.hazard.start_delay) + ONLINE_HAZARD_START_DELAY_BONUS,
        )
        hazard_manager.bullet_spawn_interval = float(level.hazard.bullet_interval) * ONLINE_HAZARD_INTERVAL_MULTIPLIER
        hazard_manager.min_bullet_interval = max(
            float(level.hazard.bullet_min_interval),
            ONLINE_HAZARD_MIN_BULLET_INTERVAL,
        )
        hazard_manager.trap_spawn_interval = float(level.hazard.trap_interval) * ONLINE_HAZARD_INTERVAL_MULTIPLIER
        hazard_manager.min_trap_interval = max(
            float(level.hazard.trap_min_interval),
            ONLINE_HAZARD_MIN_TRAP_INTERVAL,
        )
        hazard_manager.difficulty_scale_rate = max(
            float(level.hazard.difficulty_scale_rate),
            ONLINE_HAZARD_SCALE_RATE,
        )
        hazard_manager.bullet_spawn_timer = 0.0
        hazard_manager.trap_spawn_timer = 0.0
        hazard_manager.hazard_spawn_timer = 0.0
        hazard_manager.time_elapsed = 0.0

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
        seq = packet.get("s")
        reliable = bool(packet.get("r", 0))

        try:
            print(f"[NET] _handle_data: received type={t} from {addr}", flush=True)
        except Exception:
            pass

        if reliable and isinstance(seq, int):
            self._send_packet(addr, "a", seq, 0, "", {})

        def touch_addr() -> None:
            now = time.time()
            with self._lock:
                for session in self._sessions.values():
                    for entry in session.get("players", {}).values():
                        if entry.get("addr") == addr:
                            entry["last_seen"] = now
                            return

        # For TCP-authenticated clients sending their first UDP packet,
        # link their UDP address to their player entry
        def link_tcp_auth_addr() -> None:
            now = time.time()
            with self._lock:
                for session in self._sessions.values():
                    for entry in session.get("players", {}).values():
                        if entry.get("tcp_verified") and entry.get("addr") is None:
                            # This is a TCP-authenticated player sending their first UDP packet
                            entry["addr"] = addr
                            entry["last_seen"] = now
                            try:
                                player_name = next((k for k, v in session.get("players", {}).items() if v is entry), "?")
                                print(f"[TCP_UDP_LINK] Linked TCP auth player {player_name} to UDP addr {addr}", flush=True)
                            except Exception:
                                pass
                            return

        if t == "input_state":
            # For first packet from TCP-auth client, link the address
            link_tcp_auth_addr()
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
            # For first packet from TCP-auth client, link the address
            link_tcp_auth_addr()
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

        if t == "internet_auth":
            token = str(p.get("token") or "").strip()
            player = str(p.get("player") or "").strip()
            if not token or not player:
                # reject
                seq = self._next_seq()
                self._send_packet(addr, PKT_DATA, seq, 0, "internet_auth_error", {"error": "missing token/player"})
                return
            
            # Check if this session was already created via TCP handshake
            with self._lock:
                session_token_list = [t for t, s in self._sessions.items() if str(s.get("assignment", {}).get("match_id", "")) == token]
                if session_token_list:
                    # Session already exists from TCP handshake, just link the UDP address
                    session_token = session_token_list[0]
                    session = self._sessions.get(session_token)
                    if session and player in session.get("players", {}):
                        entry = session["players"][player]
                        if entry.get("addr") is None:
                            entry["addr"] = addr
                            entry["last_seen"] = time.time()
                            try:
                                print(f"[SESSION] UDP address linked for TCP-auth player: {player} -> {addr}", flush=True)
                            except Exception:
                                pass
                    # Send bootstrap snapshots
                    bootstrap_snap = self._build_snapshot(session)
                    bootstrap_world = self._build_world_snapshot(session)
                    bootstrap_dynamic = self._build_world_dynamic_snapshot(session)
                    seq = self._next_seq()
                    self._send_packet(addr, PKT_DATA, seq, 1, "snapshot", bootstrap_snap)
                    seq = self._next_seq()
                    self._send_packet(addr, PKT_DATA, seq, 1, "world_snapshot", bootstrap_world)
                    if bootstrap_dynamic is not None:
                        seq = self._next_seq()
                        self._send_packet(addr, PKT_DATA, seq, 1, "world_dynamic_snapshot", bootstrap_dynamic)
                    return
            
            # No TCP session exists, handle as new UDP-based auth (fallback)
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
                    "round_wins": [],
                    "start_time": time.time(),
                    "round_finished": False,
                    "round_restart_at": None,
                    "game_over": False,
                    "match_complete": False,
                    "end_state": None,
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
                # Ensure we have the desired number of players (fill with bots if assignment requests more)
                try:
                    desired_count = int(assignment.get("payload", {}).get("player_count", 0) or 0)
                except Exception:
                    desired_count = 0
                if desired_count and len(session_players) < desired_count:
                    idx = 1
                    # pick increasing BOT-n names until we reach desired_count
                    while len(session_players) < desired_count:
                        bot_name = f"BOT-{idx}"
                        if bot_name in session_players:
                            idx += 1
                            continue
                        bot_x = float(PLAYER_START_POS[0]) + 56.0 * float(len(session_players) + 1)
                        bot_y = float(PLAYER_START_POS[1])
                        session_players[bot_name] = {
                            "addr": None,
                            "x": bot_x,
                            "y": bot_y,
                            "last_input": {},
                            "bot": True,
                            "profile": "Bot",
                        }
                        idx += 1
                self._initialize_session_world(session)

            seq = self._next_seq()
            # Reply with ok and session id (reuse token as session id).
            # Make this reliable so the client cannot get stuck waiting for the
            # very first join confirmation.
            self._send_packet(addr, PKT_DATA, seq, 1, "internet_auth_ok", {"session_id": token})
            # Bootstrap the client immediately with a state snapshot so the
            # first match frame is not blank if the regular 10 Hz stream starts
            # a moment later.
            bootstrap_snap = self._build_snapshot(session)
            bootstrap_world = self._build_world_snapshot(session)
            bootstrap_dynamic = self._build_world_dynamic_snapshot(session)
            seq = self._next_seq()
            self._send_packet(addr, PKT_DATA, seq, 1, "snapshot", bootstrap_snap)
            seq = self._next_seq()
            self._send_packet(addr, PKT_DATA, seq, 1, "world_snapshot", bootstrap_world)
            if bootstrap_dynamic is not None:
                seq = self._next_seq()
                self._send_packet(addr, PKT_DATA, seq, 1, "world_dynamic_snapshot", bootstrap_dynamic)
            try:
                if is_new_session:
                    print(f"[SESSION] New session created: match_id={match_id}, player={player}, addr={addr}", flush=True)
                else:
                    print(f"[SESSION] Player joined existing session: match_id={match_id}, player={player}, addr={addr}, active_players={len([p for p in session_players.values() if p.get('addr')])}", flush=True)
            except Exception:
                pass
            return
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
        try:
            print(f"[NET] Hello probe from {addr}", flush=True)
        except Exception:
            pass
        seq = self._next_seq()
        self._send_packet(addr, PKT_HELLO_ACK, seq, 0, "", {})

        # Track hello reception for client timeout detection
        with self._lock:
            for session in self._sessions.values():
                players = session.get("players", {})
                for entry in players.values():
                    if entry.get("addr") == addr:
                        entry["last_seen"] = time.time()

    def _handle_disconnect(self, addr: tuple[str, int]) -> None:
        now = time.time()
        removed_sessions: list[str] = []
        with self._lock:
            for session_id, session in list(self._sessions.items()):
                players = session.get("players", {})
                matched = False
                for entry in players.values():
                    if entry.get("addr") != addr:
                        continue
                    entry["addr"] = None
                    entry["last_seen"] = now
                    entry["disconnected_at"] = now
                    matched = True
                if not matched:
                    continue
                active_players = [entry for entry in players.values() if entry.get("addr")]
                if not active_players:
                    removed_sessions.append(session_id)
            for session_id in removed_sessions:
                session = self._sessions.pop(session_id, None)
                if session is None:
                    continue
                try:
                    print(
                        f"[SESSION] Closed empty session {session_id} after disconnect (players={len(session.get('players', {}))})",
                        flush=True,
                    )
                except Exception:
                    pass

    def _handle_tcp_connection(self, client_sock: socket.socket, addr: tuple[str, int]) -> None:
        """Handle a single TCP client connection for handshake."""
        client_sock.settimeout(5.0)
        try:
            # Receive hello
            data = client_sock.recv(4096)
            if not data:
                return
            
            msg = json.loads(data.decode("utf-8").strip())
            if msg.get("type") != "hello":
                return
            
            # Send hello_ack
            hello_ack = {"type": "hello_ack"}
            client_sock.send(json.dumps(hello_ack, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n")
            
            # Receive internet_auth
            data = client_sock.recv(4096)
            if not data:
                return
            
            auth_msg = json.loads(data.decode("utf-8").strip())
            if auth_msg.get("type") != "internet_auth":
                return
            
            token = str(auth_msg.get("token") or "").strip()
            player = str(auth_msg.get("player") or "").strip()
            
            if not token or not player:
                error_msg = {"type": "internet_auth_error", "error": "missing token/player"}
                client_sock.send(json.dumps(error_msg, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n")
                return
            
            assignment = self.manager.consume_assignment(token)
            if not assignment:
                error_msg = {"type": "internet_auth_error", "error": "invalid or expired token"}
                client_sock.send(json.dumps(error_msg, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n")
                return
            
            # Create or join session
            match_id = str(assignment.get("match_id"))
            with self._lock:
                is_new_session = match_id not in self._sessions
                session = self._sessions.setdefault(match_id, {
                    "assignment": assignment,
                    "players": {},
                    "bot_names": [],
                    "bot_profiles": {},
                    "enemy_manager": None,
                    "bot_ai_timer": 0.0,
                    "created_at": time.time(),
                    "round_seq": 0,
                    "round_wins": [],
                    "start_time": time.time(),
                    "round_finished": False,
                    "round_restart_at": None,
                    "game_over": False,
                    "match_complete": False,
                    "end_state": None,
                })
                session_players = session["players"]
                spawn_x = float(PLAYER_START_POS[0]) + 48.0 * float(len(session_players))
                spawn_y = float(PLAYER_START_POS[1])
                
                # Register this client's UDP address (will be filled when UDP data arrives)
                session_players[player] = {
                    "addr": None,  # Will be set when first UDP packet arrives
                    "x": spawn_x,
                    "y": spawn_y,
                    "last_input": {},
                    "last_seen": time.time(),
                    "tcp_verified": True,  # Mark as TCP-authenticated
                }
                
                # Setup bots if first player
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
                self._tcp_addr_to_session[addr] = token
            
            # Send internet_auth_ok
            auth_ok_msg = {"type": "internet_auth_ok", "session_id": token}
            client_sock.send(json.dumps(auth_ok_msg, separators=(",", ":"), ensure_ascii=True).encode("utf-8") + b"\n")
            
            try:
                if is_new_session:
                    print(f"[TCP] New session created: match_id={match_id}, player={player}, addr={addr}", flush=True)
                else:
                    active_count = len([p for p in session_players.values() if p.get("addr")])
                    print(f"[TCP] Player joined via TCP: match_id={match_id}, player={player}, addr={addr}, active_players={active_count}", flush=True)
            except Exception:
                pass
        
        except (json.JSONDecodeError, socket.error, OSError) as e:
            try:
                print(f"[TCP_ERROR] {e}", flush=True)
            except Exception:
                pass
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def _tcp_accept_loop(self) -> None:
        """Accept TCP connections on a separate thread."""
        tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tcp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1) if hasattr(socket, 'SO_REUSEPORT') else None
        
        try:
            tcp_sock.bind((self.bind_addr, self.tcp_port))
            tcp_sock.listen(16)
            self.tcp_sock = tcp_sock
            try:
                print(f"[TCP] MatchDaemon listening on {self.bind_addr}:{self.tcp_port}", flush=True)
            except Exception:
                pass
        except (socket.error, OSError) as e:
            try:
                print(f"[TCP_ERROR] Failed to bind TCP socket: {e}", flush=True)
            except Exception:
                pass
            return
        
        tcp_sock.settimeout(0.5)
        
        while self.running:
            try:
                client_sock, addr = tcp_sock.accept()
                # Handle each client in a new thread to avoid blocking
                client_thread = threading.Thread(
                    target=self._handle_tcp_connection,
                    args=(client_sock, addr),
                    daemon=True,
                    name=f"tcp-client-{addr[0]}:{addr[1]}"
                )
                client_thread.start()
            except socket.timeout:
                continue
            except (socket.error, OSError):
                if self.running:
                    continue
                else:
                    break
        
        try:
            tcp_sock.close()
        except Exception:
            pass

    def _build_snapshot(self, session: dict) -> dict[str, Any]:
        now = time.time()
        players_list = []
        for name, entry in session.get("players", {}).items():
            players_list.append({
                "player": self._player_entry_snapshot(entry),
                "power": None,
                "bot": bool(entry.get("bot", False)),
                "name": name,
            })
        round_wins = self._ensure_round_wins(session)
        alive_count = sum(
            1
            for entry in session.get("players", {}).values()
            if not bool(entry.get("eliminated", False))
        )
        target_score = int(session.get("assignment", {}).get("payload", {}).get("target_score", 3))
        elapsed = float(now - session.get("start_time", now))
        snapshot = {
            "time_since_start": elapsed,
            "round_seq": int(session.get("round_seq", 0)),
            "paused": False,
            "game_over": bool(session.get("game_over", False)),
            "target_score": target_score,
            "round_wins": round_wins[: len(players_list)] if players_list else round_wins,
            "match_complete": bool(session.get("match_complete", False)),
            "end_state": session.get("end_state"),
            "players": players_list,
            "hud": {
                "survival_time": elapsed,
                "score": 0,
                "players_alive": int(alive_count),
                "total_players": int(len(players_list)),
                "round_wins": round_wins[: len(players_list)] if players_list else round_wins,
                "target_score": target_score,
            },
        }
        return snapshot

    def _pacman_enemy_count(self, session: dict) -> int:
        return ONLINE_PACMAN_ENEMY_COUNT if self._expected_player_count(session) >= 2 else 1

    def _tile_center(self, tile: Any) -> tuple[int, int]:
        try:
            return tile._iso_center()
        except Exception:
            return (
                int(round(float(getattr(tile, "pixel_x", PLAYER_START_POS[0])) + float(getattr(tile, "tile_width", 0)) * 0.5)),
                int(round(float(getattr(tile, "pixel_y", PLAYER_START_POS[1])) + float(getattr(tile, "tile_height", 0)) * 0.5)),
            )

    def _nearest_intact_tile_position(
        self,
        session: dict,
        desired: pygame.Vector2,
        occupied: set[tuple[int, int]],
        *,
        min_player_distance: float = 120.0,
    ) -> tuple[int, int] | None:
        tile_manager = session.get("tile_manager")
        if tile_manager is None:
            return None

        players = [
            pygame.Vector2(float(entry.get("x", PLAYER_START_POS[0])), float(entry.get("y", PLAYER_START_POS[1])))
            for entry in session.get("players", {}).values()
        ]
        candidates: list[tuple[float, tuple[int, int]]] = []
        for tile in getattr(tile_manager, "tiles", {}).values():
            if getattr(tile, "state", TileState.NORMAL) != TileState.NORMAL:
                continue
            pos = self._tile_center(tile)
            if pos in occupied:
                continue
            pos_vec = pygame.Vector2(pos)
            if players and min(pos_vec.distance_to(player_pos) for player_pos in players) < min_player_distance:
                continue
            candidates.append((pos_vec.distance_squared_to(desired), pos))

        if not candidates and min_player_distance > 0.0:
            return self._nearest_intact_tile_position(
                session,
                desired,
                occupied,
                min_player_distance=0.0,
            )
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _build_enemy_spawns(self, session: dict, count: int | None = None) -> list[tuple[int, int]]:
        enemy_count = max(1, int(count if count is not None else self._pacman_enemy_count(session)))
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
        occupied = set(positions)
        for idx, offset in enumerate(offsets):
            if len(spawns) >= enemy_count:
                break
            desired = pygame.Vector2(base_x + offset[0], base_y + offset[1])
            spawn = self._nearest_intact_tile_position(session, desired, occupied)
            if spawn is None:
                spawn = (int(round(desired.x)), int(round(desired.y)))
            spawns.append(spawn)
            occupied.add(spawn)
        while len(spawns) < enemy_count:
            px, py = positions[len(spawns) % len(positions)]
            desired = pygame.Vector2(px + 120 + len(spawns) * 30, py - 80)
            spawn = self._nearest_intact_tile_position(session, desired, occupied)
            if spawn is None:
                spawn = (int(round(desired.x)), int(round(desired.y)))
            spawns.append(spawn)
            occupied.add(spawn)
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
            self._configure_tile_manager(tile_manager, level)
            # Log initial tile position bounds after load
            if hasattr(tile_manager, 'tiles') and tile_manager.tiles:
                min_x = None
                max_x = None
                min_y = None
                max_y = None
                for tile in tile_manager.tiles.values():
                    px = int(tile.pixel_x)
                    py = int(tile.pixel_y)
                    if min_x is None or px < min_x:
                        min_x = px
                    if max_x is None or px > max_x:
                        max_x = px
                    if min_y is None or py < min_y:
                        min_y = py
                    if max_y is None or py > max_y:
                        max_y = py
                print(f"[INIT_TILE_BOUNDS] Host initial tile pixel range X=[{min_x}, {max_x}] Y=[{min_y}, {max_y}]", flush=True)

        collision_manager = CollisionManager()
        hazard_manager = HazardManager(collision_manager)
        self._configure_hazard_manager(hazard_manager, level)

        orb_manager = OrbManager(level.number)

        session["level"] = level
        session["tile_manager"] = tile_manager
        session["collision_manager"] = collision_manager
        session["hazard_manager"] = hazard_manager
        session["orb_manager"] = orb_manager
        session["original_walkable_mask"] = walkable_mask
        session["walkable_mask"] = walkable_mask
        session["walkable_bounds"] = walkable_bounds
        # Store map centering parameters so host computes same tile positions as clients
        session["map_scale_x"] = scale_x
        session["map_scale_y"] = scale_y
        session["map_offset"] = map_offset
        enemy_count = self._pacman_enemy_count(session)
        session["enemy_manager"] = (
            PacmanEnemyManager(self._build_enemy_spawns(session, enemy_count))
            if enemy_count > 0
            else None
        )
        # Projectile manager (authoritative simulation)
        try:
            session["projectile_manager"] = ProjectileManager()
        except Exception:
            session["projectile_manager"] = None
        self._ensure_round_wins(session)
        session["world_initialized"] = True

    def _build_world_snapshot(self, session: dict) -> dict[str, Any]:
        tile_manager = session.get("tile_manager")
        snapshot = {
            "time_since_start": float(time.time() - session.get("start_time", time.time())),
            "round_seq": int(session.get("round_seq", 0)),
            "tiles": tile_manager.snapshot_state() if tile_manager is not None else None,
        }
        
        # Validate walkable layer positioning on host (log tile bounds for comparison with client)
        if tile_manager is not None and hasattr(tile_manager, 'tiles') and tile_manager.tiles:
            min_x = None
            max_x = None
            min_y = None
            max_y = None
            for tile in tile_manager.tiles.values():
                px = int(tile.pixel_x)
                py = int(tile.pixel_y)
                if min_x is None or px < min_x:
                    min_x = px
                if max_x is None or px > max_x:
                    max_x = px
                if min_y is None or py < min_y:
                    min_y = py
                if max_y is None or py > max_y:
                    max_y = py
            print(f"[NET_DEBUG_HOST_VALIDATE] Tile pixel range X=[{min_x}, {max_x}] Y=[{min_y}, {max_y}]", flush=True)
        
        return snapshot

    def _build_world_dynamic_snapshot(self, session: dict) -> dict[str, Any]:
        hazard_manager = session.get("hazard_manager")
        orb_manager = session.get("orb_manager")
        enemy_manager = session.get("enemy_manager")
        proj_mgr = session.get("projectile_manager")
        proj_list = None
        if proj_mgr is not None:
            try:
                proj_list = [
                    {
                        "x": float(p.position.x),
                        "y": float(p.position.y),
                        "vx": float(p.velocity.x),
                        "vy": float(p.velocity.y),
                        "kind": p.kind.name if getattr(p, "kind", None) is not None else "ROCK",
                        "age": float(getattr(p, "age", 0.0)),
                        "lifetime": float(getattr(p, "lifetime", 0.0)),
                        "owner": str(getattr(p.owner, "name", "")) if getattr(p, "owner", None) is not None else "",
                    }
                    for p in getattr(proj_mgr, "_projectiles", [])
                    if getattr(p, "alive", False)
                ]
            except Exception:
                proj_list = None
        return {
            "time_since_start": float(time.time() - session.get("start_time", time.time())),
            "round_seq": int(session.get("round_seq", 0)),
            "hazards": hazard_manager.snapshot_state() if hazard_manager is not None else None,
            "orbs": orb_manager.snapshot_state() if orb_manager is not None else None,
            "pacman_enemies": enemy_manager.snapshot_state() if enemy_manager is not None else None,
            "projectiles": proj_list,
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
            if hasattr(player, "falling"):
                player.falling = False
            if hasattr(player, "fall_velocity"):
                player.fall_velocity = 0.0
            if hasattr(player, "velocity"):
                player.velocity.update(0, 0)
            if hasattr(player, "sync_back"):
                player.sync_back()
            return True
        except Exception:
            return False

    def _reset_session_round(self, session: dict, *, reset_match: bool = False) -> None:
        now = time.time()
        level = session.get("level") or get_level(1)
        session["round_seq"] = int(session.get("round_seq", 0)) + 1
        session["start_time"] = now
        session["round_finished"] = False
        session["round_restart_at"] = None
        session["game_over"] = False
        session["end_state"] = None
        if reset_match:
            session["match_complete"] = False
            session["round_wins"] = [0 for _ in range(max(1, len(session.get("players", {}))))]

        tile_manager = session.get("tile_manager")
        if tile_manager is not None:
            self._configure_tile_manager(tile_manager, level)
            tile_manager.reset()
            self._configure_tile_manager(tile_manager, level)

        original_mask = session.get("original_walkable_mask")
        if original_mask is not None:
            session["walkable_mask"] = (
                tile_manager.get_updated_walkable_mask(original_mask)
                if tile_manager is not None
                else original_mask
            )

        hazard_manager = session.get("hazard_manager")
        if hazard_manager is not None:
            hazard_manager.reset()
            self._configure_hazard_manager(hazard_manager, level)

        orb_manager = session.get("orb_manager")
        if orb_manager is not None:
            orb_manager.reset()

        players = session.get("players", {})
        for index, entry in enumerate(players.values()):
            entry["x"] = float(PLAYER_START_POS[0]) + 48.0 * float(index)
            entry["y"] = float(PLAYER_START_POS[1])
            entry["velocity_x"] = 0.0
            entry["velocity_y"] = 0.0
            entry["falling"] = False
            entry["fall_velocity"] = 0.0
            entry["drowning"] = False
            entry["jumping"] = False
            entry["z"] = 0.0
            entry["z_velocity"] = 0.0
            entry["on_ground"] = True
            entry["eliminated"] = False
            entry["state"] = "idle"
            entry["death_fade_alpha"] = 255
            entry["last_input"] = {}

        enemy_count = self._pacman_enemy_count(session)
        session["enemy_manager"] = (
            PacmanEnemyManager(self._build_enemy_spawns(session, enemy_count))
            if enemy_count > 0
            else None
        )
        self._ensure_round_wins(session)

    def _eliminate_proxy(self, proxy: _PlayerProxy, reason: str) -> None:
        if proxy._eliminated:
            return
        if reason in {"hit by hazard", "fell off"} and proxy.has_active_shield():
            return
        if proxy.has_extra_life() and proxy.use_life():
            if self._rescue_player_to_safe_tile(proxy):
                return
        proxy._eliminated = True
        proxy.die()
        proxy.sync_back()

    def _finish_round_if_needed(self, session: dict) -> None:
        if session.get("round_finished") or session.get("match_complete"):
            return
        if not self._session_ready(session):
            return

        players = list(session.get("players", {}).items())
        if len(players) < 2:
            return

        alive = [
            (index, name, entry)
            for index, (name, entry) in enumerate(players)
            if not bool(entry.get("eliminated", False))
        ]
        if len(alive) > 1:
            return

        wins = self._ensure_round_wins(session)
        target_score = max(1, int(session.get("assignment", {}).get("payload", {}).get("target_score", 3)))
        session["round_finished"] = True

        if len(alive) == 1:
            winner_index, winner_name, winner_entry = alive[0]
            if winner_index >= len(wins):
                wins.extend([0] * (winner_index + 1 - len(wins)))
            wins[winner_index] += 1
            if wins[winner_index] >= target_score:
                session["pending_end_state"] = {
                    "type": "victory",
                    "winner_name": str(winner_name),
                    "winner_character": str(winner_entry.get("character_name", "Caveman")),
                    "survival_time": float(time.time() - session.get("start_time", time.time())),
                }
                session["game_over"] = False
                session["round_restart_at"] = time.time() + ROUND_RESTART_DELAY
                return

        session["game_over"] = False
        session["round_restart_at"] = time.time() + ROUND_RESTART_DELAY

    def _tick_bots(self, session: dict, dt: float) -> None:
        bot_names = list(session.get("bot_names", []))
        if not bot_names:
            return

        players = session.get("players", {})
        walkable_mask = session.get("walkable_mask")
        walkable_bounds = session.get("walkable_bounds")
        hazard_manager = session.get("hazard_manager")
        enemy_manager = session.get("enemy_manager")
        bot_ai_state = session.setdefault("bot_ai_state", {})
        bot_roam_state = session.setdefault("bot_roam_state", {})
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
            bot_state = bot_ai_state.setdefault(bot_name, {"direction": pygame.Vector2(0, 0)})
            roam_state = bot_roam_state.setdefault(
                bot_name,
                {
                    "anchor_index": self._bot_seed(bot_name) % 8,
                    "time_to_retarget": BOT_ROAM_RETARGET_SECONDS,
                    "target": None,
                },
            )
            roam_target = self._select_bot_roam_target(
                bot_name,
                bot_pos,
                walkable_mask,
                walkable_bounds,
                roam_state,
                dt,
            )
            threat_vector, threat_pressure = self._bot_threat_vector(
                bot_pos,
                players,
                bot_name,
                hazard_manager,
                enemy_manager,
            )
            ally_positions = [
                pygame.Vector2(float(other.get("x", 0.0)), float(other.get("y", 0.0)))
                for other_name, other in players.items()
                if other_name != bot_name and bool(other.get("bot", False)) and not bool(other.get("eliminated", False))
            ]
            best_dir = self._choose_bot_direction(
                bot_pos,
                walkable_mask,
                walkable_bounds,
                bot_state,
                roam_target,
                threat_vector,
                threat_pressure,
                ally_positions,
            )
            bot_state["direction"] = pygame.Vector2(best_dir)
            entry["last_input"] = self._direction_to_input(best_dir)

    def _choose_bot_direction(
        self,
        bot_pos: pygame.Vector2,
        walkable_mask,
        walkable_bounds,
        bot_state: dict[str, Any],
        roam_target: pygame.Vector2,
        threat_vector: pygame.Vector2,
        threat_pressure: float,
        ally_positions: list[pygame.Vector2],
    ) -> pygame.Vector2:
        current_direction = pygame.Vector2(bot_state.get("direction", pygame.Vector2(0, 0)))
        best_dir = pygame.Vector2(0, 0)
        best_score = float("-inf")

        if threat_pressure >= 0.8 and threat_vector.length_squared() > 0:
            emergency = threat_vector.normalize()
            if self._bot_direction_score(
                bot_pos,
                emergency,
                walkable_mask,
                roam_target,
                threat_vector,
                threat_pressure,
                current_direction,
                ally_positions,
                walkable_bounds,
            ) > -0.25:
                return emergency

        for direction in BOT_CANDIDATE_DIRECTIONS:
            score = self._score_bot_direction(
                bot_pos,
                direction,
                walkable_mask,
                walkable_bounds,
                current_direction,
                roam_target,
                threat_vector,
                threat_pressure,
                ally_positions,
            )
            if score > best_score:
                best_score = score
                best_dir = pygame.Vector2(direction)

        if best_dir.length_squared() == 0:
            if current_direction.length_squared() > 0:
                best_dir = current_direction
            else:
                best_dir = pygame.Vector2(random.choice(BOT_CANDIDATE_DIRECTIONS[1:]))

        return best_dir

    def _score_bot_direction(
        self,
        bot_pos: pygame.Vector2,
        direction: pygame.Vector2,
        walkable_mask,
        walkable_bounds,
        current_direction: pygame.Vector2,
        roam_target: pygame.Vector2,
        threat_vector: pygame.Vector2,
        threat_pressure: float,
        ally_positions: list[pygame.Vector2],
    ) -> float:
        return self._bot_direction_score(
            bot_pos,
            direction,
            walkable_mask,
            roam_target,
            threat_vector,
            threat_pressure,
            current_direction,
            ally_positions,
            walkable_bounds,
        )

    def _bot_direction_score(
        self,
        bot_pos: pygame.Vector2,
        direction: pygame.Vector2,
        walkable_mask,
        roam_target: pygame.Vector2,
        threat_vector: pygame.Vector2,
        threat_pressure: float,
        current_direction: pygame.Vector2,
        ally_positions: list[pygame.Vector2],
        walkable_bounds=None,
    ) -> float:
        if direction.length_squared() == 0:
            return -0.12 + random.uniform(-0.2, 0.2)

        direction = pygame.Vector2(direction).normalize()
        probe = _PlayerProxy("bot-probe", {"x": bot_pos.x, "y": bot_pos.y}, bot=True)
        if walkable_mask is not None:
            lookahead = bot_pos + direction * BOT_LOOKAHEAD_DISTANCE
            if not probe.is_over_platform(lookahead, walkable_mask):
                return -2.0 - random.uniform(0.0, 0.5)

        distance = self._bot_walkable_distance(probe, direction, walkable_mask)
        distance_score = distance / 180.0

        roam_score = 0.0
        if roam_target is not None and roam_target.length_squared() > 0:
            to_target = roam_target - bot_pos
            if to_target.length_squared() > 0:
                roam_score = direction.dot(to_target.normalize()) * 1.15

        threat_score = 0.0
        if threat_vector.length_squared() > 0:
            threat_dir = threat_vector.normalize()
            threat_score = direction.dot(threat_dir) * (1.8 * max(0.15, threat_pressure))

        edge_score = self._bot_edge_safety_score(probe, direction, walkable_mask, walkable_bounds)

        spread_score = 0.0
        if ally_positions:
            nearest_ally = min((bot_pos.distance_to(ally_pos) for ally_pos in ally_positions), default=None)
            if nearest_ally is not None and nearest_ally < BOT_SPREAD_RADIUS:
                spread_score = (BOT_SPREAD_RADIUS - nearest_ally) / BOT_SPREAD_RADIUS

        momentum = max(0.0, direction.dot(current_direction)) * 0.2
        jitter = random.uniform(-0.14, 0.14)
        return distance_score + roam_score + threat_score + edge_score + spread_score + momentum + jitter

    def _bot_walkable_distance(self, proxy: _PlayerProxy, direction: pygame.Vector2, walkable_mask) -> float:
        if walkable_mask is None:
            return 220.0

        step = 12.0
        max_distance = 220.0
        sampled = 0.0
        probe = pygame.Vector2(proxy.position)
        while sampled < max_distance:
            probe += direction * step
            sampled += step
            if not proxy.is_over_platform(probe, walkable_mask):
                break
        return sampled

    def _bot_edge_safety_score(
        self,
        proxy: _PlayerProxy,
        direction: pygame.Vector2,
        walkable_mask,
        walkable_bounds,
    ) -> float:
        if walkable_mask is None:
            return 0.0

        danger_hits = 0
        for offset in BOT_EDGE_SAMPLE_OFFSETS:
            sample_point = proxy.position + offset + direction * 18.0
            if not proxy.is_over_platform(sample_point, walkable_mask):
                danger_hits += 1

        if danger_hits == 0:
            score = 0.45
        else:
            score = -0.45 * (danger_hits / len(BOT_EDGE_SAMPLE_OFFSETS))

        if walkable_bounds is not None and getattr(walkable_bounds, "width", 0) > 0 and getattr(walkable_bounds, "height", 0) > 0:
            center = pygame.Vector2(walkable_bounds.center)
            to_center = center - proxy.position
            if to_center.length_squared() > 0:
                score += max(0.0, direction.dot(to_center.normalize())) * 0.35
        return score

    def _bot_seed(self, bot_name: str) -> int:
        return sum(ord(ch) for ch in str(bot_name))

    def _bot_anchor_points(self, walkable_bounds) -> list[pygame.Vector2]:
        if walkable_bounds is None or getattr(walkable_bounds, "width", 0) <= 0 or getattr(walkable_bounds, "height", 0) <= 0:
            return [pygame.Vector2(PLAYER_START_POS)]

        left = float(walkable_bounds.left)
        right = float(walkable_bounds.right)
        top = float(walkable_bounds.top)
        bottom = float(walkable_bounds.bottom)
        cx, cy = walkable_bounds.center
        inset_x = max(44.0, walkable_bounds.width * 0.18)
        inset_y = max(44.0, walkable_bounds.height * 0.18)
        return [
            pygame.Vector2(cx, cy),
            pygame.Vector2(left + inset_x, top + inset_y),
            pygame.Vector2(right - inset_x, top + inset_y),
            pygame.Vector2(left + inset_x, bottom - inset_y),
            pygame.Vector2(right - inset_x, bottom - inset_y),
            pygame.Vector2(cx, top + inset_y),
            pygame.Vector2(cx, bottom - inset_y),
            pygame.Vector2(left + inset_x, cy),
            pygame.Vector2(right - inset_x, cy),
        ]

    def _select_bot_roam_target(
        self,
        bot_name: str,
        bot_pos: pygame.Vector2,
        walkable_mask,
        walkable_bounds,
        roam_state: dict[str, Any],
        dt: float,
    ) -> pygame.Vector2:
        anchors = self._bot_anchor_points(walkable_bounds)
        if not anchors:
            return pygame.Vector2(bot_pos)

        roam_state["time_to_retarget"] = float(roam_state.get("time_to_retarget", BOT_ROAM_RETARGET_SECONDS)) - float(dt)
        target = roam_state.get("target")
        target_vec = None
        if isinstance(target, (list, tuple)) and len(target) >= 2:
            try:
                target_vec = pygame.Vector2(float(target[0]), float(target[1]))
            except (TypeError, ValueError):
                target_vec = None
        elif isinstance(target, dict):
            try:
                target_vec = pygame.Vector2(float(target.get("x", bot_pos.x)), float(target.get("y", bot_pos.y)))
            except (TypeError, ValueError):
                target_vec = None

        probe = _PlayerProxy(bot_name, {"x": bot_pos.x, "y": bot_pos.y}, bot=True)
        needs_new_target = (
            target_vec is None
            or roam_state["time_to_retarget"] <= 0.0
            or bot_pos.distance_to(target_vec) < 64.0
            or (walkable_mask is not None and not probe.is_over_platform(target_vec, walkable_mask))
        )

        if needs_new_target:
            seed = self._bot_seed(bot_name)
            anchor_index = int(roam_state.get("anchor_index", seed % len(anchors)))
            anchor_index = (anchor_index + 1 + (seed % max(1, len(anchors)))) % len(anchors)
            roam_state["anchor_index"] = anchor_index
            roam_state["time_to_retarget"] = BOT_ROAM_RETARGET_SECONDS + (seed % 4) * 0.45

            desired = anchors[anchor_index]
            target_vec = self._nearest_walkable_point(probe, desired, walkable_mask)
            if target_vec is None:
                target_vec = pygame.Vector2(desired)
            roam_state["target"] = [float(target_vec.x), float(target_vec.y)]

        return pygame.Vector2(target_vec)

    def _nearest_walkable_point(
        self,
        proxy: _PlayerProxy,
        desired: pygame.Vector2,
        walkable_mask,
        max_radius: float = 220.0,
        step: float = 24.0,
    ) -> pygame.Vector2 | None:
        if walkable_mask is None:
            return pygame.Vector2(desired)

        if proxy.is_over_platform(desired, walkable_mask):
            return pygame.Vector2(desired)

        radius = step
        while radius <= max_radius:
            for angle_deg in range(0, 360, 20):
                angle = math.radians(angle_deg)
                candidate = pygame.Vector2(
                    desired.x + math.cos(angle) * radius,
                    desired.y + math.sin(angle) * radius,
                )
                if proxy.is_over_platform(candidate, walkable_mask):
                    return candidate
            radius += step
        return None

    def _entity_position(self, entity) -> pygame.Vector2 | None:
        if entity is None:
            return None
        position = getattr(entity, "position", None)
        if isinstance(position, pygame.Vector2):
            return pygame.Vector2(position)
        if isinstance(position, (tuple, list)) and len(position) >= 2:
            try:
                return pygame.Vector2(float(position[0]), float(position[1]))
            except (TypeError, ValueError):
                return None
        rect = getattr(entity, "rect", None)
        if rect is not None and hasattr(rect, "center"):
            try:
                return pygame.Vector2(rect.center)
            except Exception:
                return None
        return None

    def _bot_threat_vector(
        self,
        bot_pos: pygame.Vector2,
        players: dict[str, dict],
        bot_name: str,
        hazard_manager,
        enemy_manager,
    ) -> tuple[pygame.Vector2, float]:
        escape = pygame.Vector2(0, 0)
        pressure = 0.0

        def add_repulsion(source_pos: pygame.Vector2 | None, radius: float, strength: float) -> None:
            nonlocal escape, pressure
            if source_pos is None:
                return
            delta = bot_pos - source_pos
            distance = delta.length()
            if distance <= 0.0 or distance > radius:
                return
            influence = max(0.0, 1.0 - (distance / radius))
            escape += delta.normalize() * influence * strength
            pressure = max(pressure, influence)

        if hazard_manager is not None:
            for bullet in getattr(hazard_manager, "bullets", []):
                if not getattr(bullet, "active", False):
                    continue
                add_repulsion(self._entity_position(bullet), BOT_THREAT_RADIUS, 1.6)
            for trap in getattr(hazard_manager, "traps", []):
                if not getattr(trap, "active", False):
                    continue
                add_repulsion(self._entity_position(trap), BOT_THREAT_RADIUS, 1.3)
            for hazard in getattr(hazard_manager, "animated_hazards", []):
                if not getattr(hazard, "active", True):
                    continue
                add_repulsion(self._entity_position(hazard), BOT_THREAT_RADIUS * 0.9, 1.25)
            for explosion in getattr(hazard_manager, "explosions", []):
                add_repulsion(self._entity_position(explosion), BOT_THREAT_RADIUS * 0.85, 1.4)

        if enemy_manager is not None:
            for enemy in getattr(enemy_manager, "enemies", []):
                add_repulsion(self._entity_position(enemy), BOT_THREAT_RADIUS * 1.05, 1.5)

        for other_name, entry in players.items():
            if other_name == bot_name or bool(entry.get("eliminated", False)):
                continue
            if bool(entry.get("bot", False)):
                continue
            other_pos = pygame.Vector2(float(entry.get("x", 0.0)), float(entry.get("y", 0.0)))
            add_repulsion(other_pos, 170.0, 0.45)

        return escape, pressure

    def _direction_to_input(self, direction: pygame.Vector2) -> dict[str, bool]:
        move = {"up": False, "down": False, "left": False, "right": False}
        if direction.length_squared() == 0:
            return move

        normalized = pygame.Vector2(direction)
        if normalized.length_squared() > 0:
            normalized = normalized.normalize()
        if abs(normalized.x) >= 0.25:
            move["right"] = normalized.x > 0
            move["left"] = normalized.x < 0
        if abs(normalized.y) >= 0.25:
            move["down"] = normalized.y > 0
            move["up"] = normalized.y < 0
        if not any(move.values()):
            move["right"] = True
        return move

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _share(self, value: float, total: float, neutral: float = 0.5) -> float:
        if total <= 0:
            return float(neutral)
        return self._clamp01(float(value) / float(total))

    def _match_performance_score(
        self,
        match_stats: list[dict[str, Any]],
        local_index: int,
        winner_index: int | None,
        mvp_index: int,
        is_draw: bool = False,
    ) -> float:
        if local_index < 0 or local_index >= len(match_stats):
            return 0.5

        row = match_stats[local_index]
        total_rounds_won = sum(max(0, int(r.get("rounds_won", 0))) for r in match_stats)
        total_eliminations = sum(max(0, int(r.get("eliminations", 0))) for r in match_stats)
        total_damage_dealt = sum(max(0, int(r.get("damage_dealt", 0))) for r in match_stats)
        total_damage_taken = sum(max(0, int(r.get("damage_taken", 0))) for r in match_stats)
        total_survival = sum(max(0.0, float(r.get("survival_time", 0.0))) for r in match_stats)
        total_deaths = sum(max(0, int(r.get("deaths", 0))) for r in match_stats)

        rounds_share = self._share(max(0, int(row.get("rounds_won", 0))), total_rounds_won)
        elimination_share = self._share(max(0, int(row.get("eliminations", 0))), total_eliminations)
        dealt_share = self._share(max(0, int(row.get("damage_dealt", 0))), total_damage_dealt)
        taken_efficiency = 1.0 - self._share(max(0, int(row.get("damage_taken", 0))), total_damage_taken)
        survival_share = self._share(max(0.0, float(row.get("survival_time", 0.0))), total_survival)
        death_efficiency = 1.0 - self._share(max(0, int(row.get("deaths", 0))), total_deaths)

        base_score = (
            0.24 * rounds_share
            + 0.17 * elimination_share
            + 0.17 * dealt_share
            + 0.14 * taken_efficiency
            + 0.14 * survival_share
            + 0.14 * death_efficiency
        )
        win_bonus = 0.12 if (winner_index is not None and local_index == winner_index) else 0.0
        mvp_bonus = 0.08 if local_index == mvp_index else 0.0
        draw_bonus = 0.03 if is_draw else 0.0
        return self._clamp01(base_score + win_bonus + mvp_bonus + draw_bonus)

    def _rr_caps_for_target_score(
        self,
        target_score: int | None = None,
        player_count: int | None = None,
    ) -> tuple[int, int]:
        score_to_win = int(target_score if target_score is not None else 3)
        players_total = int(player_count if player_count is not None else 2)
        min_target = 3
        max_target = 20
        min_win_cap = 12
        max_win_cap = 45
        min_lose_cap = 8
        max_lose_cap = 40

        if max_target <= min_target:
            return max_win_cap, max_lose_cap

        t = (score_to_win - min_target) / float(max_target - min_target)
        t = max(0.0, min(1.0, t))
        base_win_cap = int(round(min_win_cap + (max_win_cap - min_win_cap) * t))
        base_lose_cap = int(round(min_lose_cap + (max_lose_cap - min_lose_cap) * t))

        # Larger lobbies should have slightly higher RR swings at the same round target.
        player_t = (players_total - 2) / 2.0
        player_t = max(0.0, min(1.0, player_t))
        win_cap = int(round(base_win_cap * (1.0 + 0.35 * player_t)))
        lose_cap = int(round(base_lose_cap * (1.0 + 0.30 * player_t)))
        return win_cap, lose_cap

    def _compute_rr_delta(
        self,
        match_stats: list[dict[str, Any]],
        local_index: int,
        winner_index: int | None,
        mvp_index: int,
        target_score: int,
        is_draw: bool = False,
    ) -> int:
        if is_draw:
            return 0

        max_gain, max_loss = self._rr_caps_for_target_score(
            target_score,
            player_count=len(match_stats),
        )
        score = self._match_performance_score(match_stats, local_index, winner_index, mvp_index, is_draw=is_draw)
        won_match = winner_index is not None and local_index == winner_index
        if won_match:
            gain = int(round(score * float(max_gain)))
            return max(0, min(max_gain, gain))

        loss = int(round((1.0 - score) * float(max_loss)))
        return -max(0, min(max_loss, loss))

    def _tick_physics(self, dt: float) -> None:
        dt = min(MAX_TICK_DT, max(0.0, float(dt)))
        if dt <= 0.0:
            return
        with self._lock:
            for session in list(self._sessions.values()):
                players = session.get("players", {})
                self._initialize_session_world(session)
                # If waiting for players and queue timeout elapsed, fill remaining
                # slots with bots up to the requested player_count.
                try:
                    payload = session.get("assignment", {}).get("payload", {}) or {}
                    desired_count = int(payload.get("player_count", 0) or 0)
                except Exception:
                    desired_count = 0
                if desired_count and not self._session_ready(session):
                    created_at = float(session.get("created_at", session.get("start_time", time.time())))
                    if time.time() - created_at >= QUEUE_FILL_TIMEOUT:
                        # Count currently registered human players (addr present)
                        humans = [e for e in players.values() if not bool(e.get("bot", False)) and e.get("addr")]
                        missing = max(0, desired_count - max(1, len(players)))
                        # If there are fewer humans than expected, add bots to reach desired_count
                        if len(humans) < desired_count:
                            idx = 1
                            while len([k for k in players.keys() if k.startswith("BOT-")]) < (desired_count - len(humans)):
                                bot_name = f"BOT-{idx}"
                                if bot_name in players:
                                    idx += 1
                                    continue
                                spawn_x = float(PLAYER_START_POS[0]) + 56.0 * float(len(players) + 1)
                                spawn_y = float(PLAYER_START_POS[1])
                                players[bot_name] = {"addr": None, "x": spawn_x, "y": spawn_y, "last_input": {}, "bot": True, "profile": "Bot"}
                                idx += 1
                if not self._session_ready(session):
                    session["start_time"] = time.time()
                    continue

                restart_at = session.get("round_restart_at")
                if restart_at is not None and time.time() >= float(restart_at):
                    pending_end_state = session.pop("pending_end_state", None)
                    if isinstance(pending_end_state, dict):
                        session["match_complete"] = True
                        session["game_over"] = True
                        session["end_state"] = pending_end_state
                        session["round_restart_at"] = None
                        try:
                            players = session.get("players", {})
                            player_items = list(players.items())
                            round_wins = self._ensure_round_wins(session)
                            target_score = max(1, int(session.get("assignment", {}).get("payload", {}).get("target_score", 3)))
                            mode = str(session.get("assignment", {}).get("payload", {}).get("mode", "ranked")).strip().lower()
                            ranked_mode = mode != "unranked"
                            match_stats: list[dict[str, Any]] = []
                            for idx, (pname, pentry) in enumerate(player_items):
                                match_stats.append(
                                    {
                                        "username": str(pname),
                                        "character": str(pentry.get("character_name", "Caveman")),
                                        "rounds_played": int(max(0, round_wins[idx] if idx < len(round_wins) else 0)),
                                        "rounds_won": int(max(0, round_wins[idx] if idx < len(round_wins) else 0)),
                                        "eliminations": int(max(0, pentry.get("eliminations", 0))),
                                        "deaths": int(max(0, pentry.get("deaths", 0))),
                                        "damage_dealt": int(max(0, pentry.get("damage_dealt", 0))),
                                        "damage_taken": int(max(0, pentry.get("damage_taken", 0))),
                                        "survival_time": float(max(0.0, time.time() - float(session.get("start_time", time.time())))),
                                    }
                                )

                            winner_name = str(pending_end_state.get("winner_name") or "")
                            winner_index = None
                            if winner_name:
                                for idx, (pname, _) in enumerate(player_items):
                                    if pname == winner_name:
                                        winner_index = idx
                                        break
                            mvp_index = 0
                            if match_stats:
                                mvp_index = 0
                                best_score = -1.0
                                for idx in range(len(match_stats)):
                                    score = self._match_performance_score(match_stats, idx, winner_index, mvp_index, is_draw=False)
                                    if score > best_score:
                                        best_score = score
                                        mvp_index = idx

                            rr_results: dict[str, dict[str, Any]] = {}
                            for idx, (pname, pentry) in enumerate(player_items):
                                if bool(pentry.get("bot", False)):
                                    continue
                                if not isinstance(pname, str) or not pname.strip():
                                    continue
                                rr_before = 1000
                                rr_after = 1000
                                rr_delta = self._compute_rr_delta(match_stats, idx, winner_index, mvp_index, target_score, is_draw=False) if ranked_mode else 0
                                if ranked_mode and self.account_store is not None:
                                    try:
                                        profile = self.account_store.get_profile(pname)
                                        if profile is not None:
                                            rr_before = int(profile.rr)
                                        update_result = self.account_store.apply_sync_event(
                                            {
                                                "username": pname,
                                                "event_type": "stat_delta",
                                                "payload": {
                                                    "ranked": True,
                                                    "rr_delta": int(rr_delta),
                                                    "rr_after": max(0, int(rr_before + rr_delta)),
                                                    "damage_dealt": 0,
                                                    "damage_taken": 0,
                                                    "eliminations": 0,
                                                    "deaths": 0,
                                                    "rounds_played": int(max(0, match_stats[idx].get("rounds_played", 0))),
                                                    "rounds_won": int(max(0, match_stats[idx].get("rounds_won", 0))),
                                                    "matches_played": 1,
                                                    "matches_won": 1 if winner_index is not None and idx == winner_index else 0,
                                                    "mvp_count": 1 if idx == mvp_index else 0,
                                                    "updated_at": time.time(),
                                                },
                                            }
                                        )
                                        profile_after = update_result.get("profile") if isinstance(update_result, dict) else None
                                        if profile_after is not None:
                                            rr_after = int(getattr(profile_after, "rr", rr_after))
                                        else:
                                            rr_after = max(0, rr_before + rr_delta)
                                    except Exception:
                                        rr_after = max(0, rr_before + rr_delta)
                                elif ranked_mode:
                                    rr_after = max(0, rr_before + rr_delta)
                                rr_results[pname] = {
                                    "rr_before": int(rr_before),
                                    "rr_after": int(rr_after),
                                    "rr_delta": int(rr_delta if ranked_mode else 0),
                                }

                            result_id = f"match_result_server_{int(time.time() * 1000)}"
                            match_result = {
                                "result_id": result_id,
                                "winner_index": int(winner_index) if winner_index is not None else -1,
                                "mvp_index": int(mvp_index),
                                "is_draw": False,
                                "match_complete": True,
                                "ranked_mode": bool(ranked_mode),
                                "target_score": int(target_score),
                                "round_wins": [int(v) for v in round_wins],
                                "match_stats": match_stats,
                                "rr_results": rr_results,
                                "winner_name": winner_name,
                            }
                            for _, pentry in player_items:
                                addr = pentry.get("addr")
                                if not addr:
                                    continue
                                seq = self._next_seq()
                                try:
                                    self._send_packet(addr, PKT_DATA, seq, 1, "match_result", match_result)
                                except Exception:
                                    pass
                            session["match_result_sent"] = True
                        except Exception:
                            pass
                    else:
                        self._reset_session_round(session)
                        players = session.get("players", {})

                if session.get("round_finished"):
                    current_proxies = [
                        _PlayerProxy(name, entry, bot=bool(entry.get("bot", False)))
                        for name, entry in players.items()
                    ]
                    for proxy in current_proxies:
                        if proxy._eliminated:
                            proxy.update_death(dt)
                        proxy.sync_back()
                    continue

                self._tick_bots(session, dt)
                player_proxies: dict[str, _PlayerProxy] = {
                    name: _PlayerProxy(name, entry, bot=bool(entry.get("bot", False)))
                    for name, entry in players.items()
                }
                walkable_mask = session.get("walkable_mask")
                level = session.get("level")
                for name, entry in players.items():
                    proxy = player_proxies.get(name)
                    if proxy is None:
                        continue
                    if proxy._eliminated:
                        proxy.update_death(dt)
                        proxy.sync_back()
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
                    if proxy.falling:
                        proxy.update_fall(dt)
                        if proxy.position.y > WINDOW_SIZE[1] + 100:
                            self._eliminate_proxy(proxy, "fell off")
                        proxy.rect.center = (round(proxy.position.x), round(proxy.position.y))
                        proxy.sync_back()
                        continue

                    speed_multiplier = float(proxy._orb_speed_boost or 1.0)
                    if proxy.bot and level is not None:
                        speed_multiplier *= float(getattr(level.ai, "speed_multiplier", 1.0))
                    speed = float(PLAYER_SPEED) * speed_multiplier
                    if proxy._freeze_timer > 0.0:
                        speed *= 0.2
                    move_vector = pygame.Vector2(0.0, 0.0)
                    if left:
                        move_vector.x -= 1.0
                    if right:
                        move_vector.x += 1.0
                    if up:
                        move_vector.y -= 1.0
                    if down:
                        move_vector.y += 1.0

                    left_playable = False
                    if move_vector.length_squared() > 0.0:
                        move_vector = move_vector.normalize()
                        proxy.velocity = move_vector * speed
                        if abs(move_vector.y) >= abs(move_vector.x):
                            proxy.facing = "down" if move_vector.y > 0 else "up"
                        else:
                            proxy.facing = "right" if move_vector.x > 0 else "left"
                        left_playable = not proxy.attempt_move(proxy.velocity * dt, walkable_mask)
                        proxy.state = "run"
                    else:
                        proxy.velocity.update(0, 0)
                        proxy.state = "idle"
                        left_playable = not proxy.is_over_platform(proxy.position, walkable_mask)

                    if left_playable:
                        proxy.start_fall()
                        proxy.update_fall(dt)
                        if proxy.position.y > WINDOW_SIZE[1] + 100:
                            self._eliminate_proxy(proxy, "fell off")

                    proxy.rect.center = (round(proxy.position.x), round(proxy.position.y))
                    # Handle shoot input edge (spawn projectiles on press)
                    inp = entry.get("last_input") or {}
                    try:
                        shoot_now = bool(inp.get("shoot", False))
                    except Exception:
                        shoot_now = False
                    prev_shoot = bool(entry.get("_last_shoot", False))
                    if shoot_now and not prev_shoot:
                        # Determine direction from directional input if present
                        try:
                            dx = float(bool(inp.get("right"))) - float(bool(inp.get("left")))
                            dy = float(bool(inp.get("down"))) - float(bool(inp.get("up")))
                            direction = pygame.Vector2(dx, dy) if (dx != 0.0 or dy != 0.0) else None
                        except Exception:
                            direction = None
                        proj_mgr = session.get("projectile_manager")
                        if proj_mgr is not None:
                            try:
                                proj_mgr.fire(proxy, direction)
                            except Exception:
                                pass
                    entry["_last_shoot"] = shoot_now
                    proxy.sync_back()

                tile_manager = session.get("tile_manager")
                if tile_manager is not None:
                    tile_manager.update(dt)
                    original_mask = session.get("original_walkable_mask")
                    if original_mask is not None:
                        session["walkable_mask"] = tile_manager.get_updated_walkable_mask(original_mask)
                        walkable_mask = session.get("walkable_mask")

                hazard_manager = session.get("hazard_manager")
                if hazard_manager is not None and not session.get("round_finished"):
                    hazard_manager.update(dt)

                enemy_manager = session.get("enemy_manager")
                if enemy_manager is None and not session.get("round_finished"):
                    enemy_count = self._pacman_enemy_count(session)
                    enemy_manager = PacmanEnemyManager(self._build_enemy_spawns(session, enemy_count))
                    session["enemy_manager"] = enemy_manager

                current_proxies = list(player_proxies.values())
                self.eliminated_players = [proxy for proxy in current_proxies if proxy._eliminated]

                # Advance authoritative projectile simulation
                proj_mgr = session.get("projectile_manager")
                if proj_mgr is not None:
                    try:
                        class _GameLike:
                            pass

                        g = _GameLike()
                        g.players = current_proxies
                        g.eliminated_players = self.eliminated_players
                        g.pacman_enemy_manager = session.get("enemy_manager")
                        # Provide _eliminate_player hook expected by projectiles
                        def _elim(p, reason=""):
                            try:
                                self._eliminate_proxy(p, reason)
                            except Exception:
                                pass
                        g._eliminate_player = _elim
                        proj_mgr.update(dt, g)
                    except Exception:
                        pass

                if hazard_manager is not None and not session.get("round_finished"):
                    for proxy in current_proxies:
                        if proxy._eliminated:
                            continue
                        if hazard_manager.check_player_collision(proxy):
                            self._eliminate_proxy(proxy, "hit by hazard")
                            if proxy._eliminated and proxy not in self.eliminated_players:
                                self.eliminated_players.append(proxy)

                if enemy_manager is not None and not session.get("round_finished"):
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
                            self._eliminate_proxy(proxy, "hit by hazard")
                            if proxy._eliminated and proxy not in self.eliminated_players:
                                self.eliminated_players.append(proxy)

                orb_manager = session.get("orb_manager")
                if orb_manager is not None and not session.get("round_finished"):
                    orb_manager.update(dt, session.get("walkable_bounds"), current_proxies, self)

                for proxy in current_proxies:
                    proxy.sync_back()

                self._finish_round_if_needed(session)

                # Keep round_seq stable during a running match.
                # The client uses round_seq as a round-transition marker, so
                # changing it every tick makes the client reset its world state
                # continuously.

    def _cleanup_stale_sessions(self, now: float) -> None:
        """Remove sessions with no active players for >30 seconds (was 90s)."""
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
                
                # Session is stale if created >30s ago AND no active players
                created_at = session.get("created_at", now)
                session_age = now - created_at
                if session_age > 30.0 and not has_active_player:
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

        # Start TCP server thread for handshakes
        tcp_thread = threading.Thread(target=self._tcp_accept_loop, daemon=True, name="tcp-accept")
        tcp_thread.start()

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
                    packet = json.loads(raw.decode("utf-8"))
                except Exception:
                    # Some clients/middleboxes may alter probe payload formatting;
                    # still answer hello probes to establish UDP reachability.
                    if self._looks_like_hello_probe(raw):
                        self._handle_hello(addr)
                    continue
                    continue
                kind = packet.get("k")
                if kind == PKT_HELLO:
                    self._handle_hello(addr)
                    continue
                if kind == PKT_DISCONNECT:
                    self._handle_disconnect(addr)
                    continue
                if kind == PKT_DATA:
                    self._handle_data(addr, packet)
                elif kind == PKT_FRAGMENT:
                    # ignore fragments in this MVP
                    continue
        finally:
            # Graceful shutdown: signal all sessions to close and wait a bit
            with self._lock:
                for session in list(self._sessions.values()):
                    for pname, entry in session.get("players", {}).items():
                        addr = entry.get("addr")
                        if addr:
                            seq = self._next_seq()
                            try:
                                self._send_packet(addr, PKT_DATA, seq, 0, "game_end", {})
                            except Exception:
                                pass
                self._sessions.clear()
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
