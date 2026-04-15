"""
Online multiplayer support for Grid Survival.
Provides internet matchmaking, lobby system, and relay-free direct connection.
"""

from __future__ import annotations

import json
import queue
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional

DEFAULT_ONLINE_PORT = 5777
LOBBY_SERVER_PORT = 5778
DISCOVERY_MAGIC = "grid_survival_online_v1"


@dataclass
class LobbyPlayer:
    """Player in a lobby."""
    player_id: int
    name: str
    character: str
    is_ready: bool = False
    address: Optional[tuple] = None


@dataclass
class Lobby:
    """Game lobby with players."""
    lobby_id: str
    host_name: str
    max_players: int
    players: list[LobbyPlayer]
    status: str = "waiting"  # waiting, starting, in_game


class OnlineLobbyManager:
    """Manages online lobby creation and joining."""

    def __init__(self):
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self._receive_thread: Optional[threading.Thread] = None
        self.message_queue: queue.Queue[dict] = queue.Queue()
        self.lobby: Optional[Lobby] = None
        self.is_host = False
        self.player_id = 0
        self.player_name = "Player"
        self._send_lock = threading.Lock()

    def connect_to_server(self, server_address: str, port: int = LOBBY_SERVER_PORT) -> bool:
        """Connect to the matchmaking server."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            self.socket.connect((server_address, port))
            self.socket.settimeout(0.25)
            self.connected = True
            self.running = True
            self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._receive_thread.start()
            return True
        except (socket.error, OSError) as Exception:
            self.connected = False
            return False

    def _receive_loop(self) -> None:
        while self.running and self.connected and self.socket:
            try:
                length_bytes = self._recv_exact(4)
                if not length_bytes:
                    break
                length = int.from_bytes(length_bytes, "big")
                if length <= 0:
                    continue
                payload = self._recv_exact(length)
                if not payload:
                    break
                message = json.loads(payload.decode("utf-8"))
                if isinstance(message, dict):
                    self.message_queue.put(message)
            except (socket.error, OSError, json.JSONDecodeError):
                break
        self.connected = False
        self.running = False

    def _recv_exact(self, size: int) -> Optional[bytes]:
        if not self.socket:
            return None
        chunks = bytearray()
        while len(chunks) < size and self.running:
            try:
                chunk = self.socket.recv(size - len(chunks))
            except socket.timeout:
                continue
            except (socket.error, OSError):
                return None
            if not chunk:
                return None
            chunks.extend(chunk)
        return bytes(chunks)

    def send_message(self, message_type: str, **payload: Any) -> bool:
        """Send a message to the server."""
        if not self.connected or not self.socket:
            return False
        try:
            message = {"type": message_type, **payload}
            encoded = json.dumps(message, separators=(",", ":")).encode("utf-8")
            header = len(encoded).to_bytes(4, "big")
            with self._send_lock:
                self.socket.sendall(header)
                self.socket.sendall(encoded)
            return True
        except (socket.error, BrokenPipeError, OSError):
            self.connected = False
            return False

    def get_messages(self) -> list[dict]:
        """Get all queued messages."""
        messages = []
        while not self.message_queue.empty():
            try:
                messages.append(self.message_queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def create_lobby(self, name: str, max_players: int = 8) -> bool:
        """Create a new lobby."""
        if not self.send_message("create_lobby", lobby_name=name, max_players=max_players):
            return False
        time.sleep(0.1)
        for msg in self.get_messages():
            if msg.get("type") == "lobby_created":
                self.lobby = Lobby(
                    lobby_id=msg.get("lobby_id", ""),
                    host_name=name,
                    max_players=max_players,
                    players=[LobbyPlayer(0, name, "Caveman", True)],
                )
                self.is_host = True
                self.player_id = 0
                return True
        return False

    def join_lobby(self, lobby_id: str, player_name: str) -> bool:
        """Join an existing lobby."""
        self.player_name = player_name
        if not self.send_message("join_lobby", lobby_id=lobby_id, player_name=player_name):
            return False
        time.sleep(0.1)
        for msg in self.get_messages():
            if msg.get("type") == "lobby_joined":
                self.lobby = Lobby(
                    lobby_id=lobby_id,
                    host_name=msg.get("host_name", ""),
                    max_players=msg.get("max_players", 8),
                    players=[],
                )
                self.is_host = False
                self.player_id = msg.get("player_id", 1)
                return True
        return False

    def list_lobbies(self) -> list[dict]:
        """Get list of available lobbies."""
        if not self.send_message("list_lobbies"):
            return []
        time.sleep(0.2)
        lobbies = []
        for msg in self.get_messages():
            if msg.get("type") == "lobby_list":
                lobbies = msg.get("lobbies", [])
        return lobbies

    def set_ready(self, ready: bool) -> bool:
        """Set player ready status."""
        return self.send_message("set_ready", ready=ready)

    def leave_lobby(self) -> bool:
        """Leave current lobby."""
        if not self.send_message("leave_lobby"):
            return False
        self.lobby = None
        return True

    def start_game(self, host_address: str, host_port: int = DEFAULT_ONLINE_PORT) -> bool:
        """Start the game and return connection info."""
        if not self.send_message("start_game"):
            return False
        time.sleep(0.1)
        for msg in self.get_messages():
            if msg.get("type") == "game_starting":
                return True
        return False

    def disconnect(self) -> None:
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None
        self.connected = False
        if self._receive_thread and self._receive_thread.is_alive():
            self._receive_thread.join(timeout=1.0)


class OnlineHost:
    """Host for direct online multiplayer without relay server."""

    def __init__(self, port: int = DEFAULT_ONLINE_PORT):
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.listening = False
        self.clients: dict[int, socket.socket] = {}
        self.client_info: dict[int, dict] = {}
        self._next_client_id = 0
        self.running = False
        self._receive_threads: dict[int, threading.Thread] = {}
        self.message_queues: dict[int, queue.Queue] = {}

    def start_hosting(self, advertised_name: str = "Online Game") -> bool:
        """Start hosting on the specified port."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(("0.0.0.0", self.port))
            self.server_socket.listen(8)
            self.server_socket.setblocking(False)
            self.listening = True
            self.running = True
            return True
        except (socket.error, OSError):
            self.listening = False
            return False

    def poll_connections(self) -> list[int]:
        """Accept any waiting connections."""
        new_ids = []
        if not self.server_socket or not self.listening:
            return new_ids
        
        while len(self.clients) < 8:
            try:
                client_socket, addr = self.server_socket.accept()
            except BlockingIOError:
                break
            except (socket.error, OSError):
                break

            client_id = self._next_client_id
            self._next_client_id += 1
            
            client_socket.settimeout(0.25)
            self.clients[client_id] = client_socket
            self.client_info[client_id] = {"address": addr, "name": f"Player{client_id + 1}"}
            self.message_queues[client_id] = queue.Queue()
            
            thread = threading.Thread(target=self._client_receive_loop, args=(client_id,), daemon=True)
            thread.start()
            self._receive_threads[client_id] = thread
            
            new_ids.append(client_id)
        
        return new_ids

    def _client_receive_loop(self, client_id: int) -> None:
        socket = self.clients.get(client_id)
        if not socket:
            return
        
        while self.running and client_id in self.clients:
            try:
                length_bytes = self._recv_exact(socket, 4)
                if not length_bytes:
                    break
                length = int.from_bytes(length_bytes, "big")
                if length <= 0:
                    continue
                payload = self._recv_exact(socket, length)
                if not payload:
                    break
                message = json.loads(payload.decode("utf-8"))
                if isinstance(message, dict) and client_id in self.message_queues:
                    self.message_queues[client_id].put(message)
            except (socket.error, OSError, json.JSONDecodeError):
                break
        
        self._remove_client(client_id)

    def _recv_exact(self, sock: socket.socket, size: int) -> Optional[bytes]:
        chunks = bytearray()
        while len(chunks) < size and self.running:
            try:
                chunk = sock.recv(size - len(chunks))
            except socket.timeout:
                continue
            except (socket.error, OSError):
                return None
            if not chunk:
                return None
            chunks.extend(chunk)
        return bytes(chunks)

    def _remove_client(self, client_id: int) -> None:
        if client_id in self.clients:
            try:
                self.clients[client_id].close()
            except OSError:
                pass
            del self.clients[client_id]
        if client_id in self.client_info:
            del self.client_info[client_id]
        if client_id in self.message_queues:
            del self.message_queues[client_id]
        if client_id in self._receive_threads:
            del self._receive_threads[client_id]

    def get_client_messages(self, client_id: int) -> list[dict]:
        """Get messages from a specific client."""
        if client_id not in self.message_queues:
            return []
        messages = []
        while not self.message_queues[client_id].empty():
            try:
                messages.append(self.message_queues[client_id].get_nowait())
            except queue.Empty:
                break
        return messages

    def broadcast_message(self, message_type: str, **payload: Any) -> int:
        """Send message to all clients."""
        sent = 0
        for client_id, sock in self.clients.items():
            try:
                message = {"type": message_type, **payload}
                encoded = json.dumps(message, separators=(",", ":")).encode("utf-8")
                header = len(encoded).to_bytes(4, "big")
                sock.sendall(header)
                sock.sendall(encoded)
                sent += 1
            except (socket.error, OSError):
                self._remove_client(client_id)
        return sent

    def get_client_count(self) -> int:
        return len(self.clients)

    def disconnect(self) -> None:
        self.running = False
        for client_id in list(self.clients.keys()):
            self._remove_client(client_id)
        if self.server_socket:
            try:
                self.server_socket.close()
            except OSError:
                pass
            self.server_socket = None
        self.listening = False


class OnlineClient:
    """Client for direct online multiplayer."""

    def __init__(self):
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self._receive_thread: Optional[threading.Thread] = None
        self.message_queue: queue.Queue = queue.Queue()
        self._send_lock = threading.Lock()

    def connect(self, host: str, port: int = DEFAULT_ONLINE_PORT) -> bool:
        """Connect to an online host."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            self.socket.connect((host, port))
            self.socket.settimeout(0.25)
            self.connected = True
            self.running = True
            self._receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._receive_thread.start()
            return True
        except (socket.error, OSError):
            self.connected = False
            return False

    def _receive_loop(self) -> None:
        while self.running and self.connected and self.socket:
            try:
                length_bytes = self._recv_exact(4)
                if not length_bytes:
                    break
                length = int.from_bytes(length_bytes, "big")
                if length <= 0:
                    continue
                payload = self._recv_exact(length)
                if not payload:
                    break
                message = json.loads(payload.decode("utf-8"))
                if isinstance(message, dict):
                    self.message_queue.put(message)
            except (socket.error, OSError, json.JSONDecodeError):
                break
        self.connected = False
        self.running = False

    def _recv_exact(self, size: int) -> Optional[bytes]:
        if not self.socket:
            return None
        chunks = bytearray()
        while len(chunks) < size and self.running:
            try:
                chunk = self.socket.recv(size - len(chunks))
            except socket.timeout:
                continue
            except (socket.error, OSError):
                return None
            if not chunk:
                return None
            chunks.extend(chunk)
        return bytes(chunks)

    def send_message(self, message_type: str, **payload: Any) -> bool:
        """Send a message to the host."""
        if not self.connected or not self.socket:
            return False
        try:
            message = {"type": message_type, **payload}
            encoded = json.dumps(message, separators=(",", ":")).encode("utf-8")
            header = len(encoded).to_bytes(4, "big")
            with self._send_lock:
                self.socket.sendall(header)
                self.socket.sendall(encoded)
            return True
        except (socket.error, OSError):
            self.connected = False
            return False

    def get_messages(self) -> list[dict]:
        messages = []
        while not self.message_queue.empty():
            try:
                messages.append(self.message_queue.get_nowait())
            except queue.Empty:
                break
        return messages

    def disconnect(self) -> None:
        self.running = False
        if self.socket:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.socket.close()
            except OSError:
                pass
            self.socket = None
        self.connected = False
        if self._receive_thread and self._receive_thread.is_alive():
            self._receive_thread.join(timeout=1.0)