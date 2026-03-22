"""
LAN multiplayer networking for Grid Survival.
Implements host/client connection and state synchronization.
"""

import socket
import json
import threading
import queue
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass
class PlayerState:
    """Updated player state with timestamp for interpolation."""
    x: float
    y: float
    facing: str
    state: str
    falling: bool
    drowning: bool
    eliminated: bool
    timestamp: float = 0.0  # Added to track packet timing

class NetworkManager:
    """Base network manager for multiplayer."""
    
    def __init__(self):
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.running = False
        self.receive_thread: Optional[threading.Thread] = None
        self.message_queue = queue.Queue()
        self.player_states: Dict[str, PlayerState] = {}
    
    def send_player_state(self, player_id: str, state: PlayerState):
        """Send player state to connected peer."""
        if not self.connected or not self.socket:
            return
        
        try:
            message = {
                'type': 'player_state',
                'player_id': player_id,
                'state': asdict(state)
            }
            data = json.dumps(message).encode('utf-8')
            # Send message length first, then message
            length = len(data)
            self.socket.sendall(length.to_bytes(4, 'big'))
            self.socket.sendall(data)
        except (socket.error, BrokenPipeError) as e:
            print(f"Error sending player state: {e}")
            self.connected = False
    
    def get_messages(self):
        """Get all queued messages."""
        messages = []
        while not self.message_queue.empty():
            try:
                messages.append(self.message_queue.get_nowait())
            except queue.Empty:
                break
        return messages
    
    def _receive_loop(self):
        """Background thread for receiving messages."""
        while self.running and self.connected:
            try:
                # Receive message length
                length_bytes = self._recv_exact(4)
                if not length_bytes:
                    break
                
                length = int.from_bytes(length_bytes, 'big')
                
                # Receive message data
                data = self._recv_exact(length)
                if not data:
                    break
                
                message = json.loads(data.decode('utf-8'))
                self.message_queue.put(message)
                
            except (socket.error, json.JSONDecodeError) as e:
                print(f"Error receiving data: {e}")
                break
        
        self.connected = False
    
    def _recv_exact(self, num_bytes: int) -> Optional[bytes]:
        """Receive exact number of bytes."""
        data = b''
        while len(data) < num_bytes:
            try:
                chunk = self.socket.recv(num_bytes - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.error:
                return None
        return data
    
    def disconnect(self):
        """Disconnect from network."""
        self.running = False
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)


class NetworkHost(NetworkManager):
    """Host side of network multiplayer."""
    
    def __init__(self, port: int = 5555):
        super().__init__()
        self.port = port
        self.server_socket: Optional[socket.socket] = None
    
    def start_hosting(self) -> bool:
        """Start hosting a game."""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(1)
            self.server_socket.settimeout(30.0)  # 30 second timeout for accepting
            
            print(f"Hosting on port {self.port}, waiting for client...")
            
            # Accept connection
            self.socket, addr = self.server_socket.accept()
            self.socket.settimeout(None)  # Remove timeout after connection
            self.connected = True
            self.running = True
            
            print(f"Client connected from {addr}")
            
            # Start receive thread
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            return True
            
        except socket.timeout:
            print("Connection timeout - no client connected")
            return False
        except socket.error as e:
            print(f"Error starting host: {e}")
            return False
    
    def disconnect(self):
        """Disconnect and close server."""
        super().disconnect()
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass


class NetworkClient(NetworkManager):
    """Client side of network multiplayer."""
    
    def __init__(self):
        super().__init__()
    
    def connect_to_host(self, host: str, port: int = 5555) -> bool:
        """Connect to a host."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)  # 10 second connection timeout
            
            print(f"Connecting to {host}:{port}...")
            self.socket.connect((host, port))
            self.socket.settimeout(None)  # Remove timeout after connection
            
            self.connected = True
            self.running = True
            
            print(f"Connected to host at {host}:{port}")
            
            # Start receive thread
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            return True
            
        except socket.timeout:
            print("Connection timeout")
            return False
        except socket.error as e:
            print(f"Error connecting to host: {e}")
            return False


def get_local_ip() -> str:
    """Get local IP address for hosting."""
    try:
        # Create a socket to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except:
        return "127.0.0.1"
