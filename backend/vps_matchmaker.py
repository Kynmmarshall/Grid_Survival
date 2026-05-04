import socket
import threading
import time
import json
import logging
import os

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configuration
SERVER_HOST = os.getenv("MATCHMAKER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("MATCHMAKER_PORT", "5557"))
CLIENT_TIMEOUT = 15.0  # seconds until a client is considered disconnected

# In-memory store for connected clients
# Structure: {"username": {"ip": str, "port": int, "last_seen": float, "state": str}}
clients = {}
clients_lock = threading.Lock()


def cleanup_stale_clients():
    """Background task to remove clients that haven't sent a keepalive recently."""
    while True:
        time.sleep(5)
        now = time.time()
        with clients_lock:
            stale_users = [
                username for username, data in clients.items()
                if now - data["last_seen"] > CLIENT_TIMEOUT
            ]
            for username in stale_users:
                logging.info(f"Client '{username}' timed out. Removing from lobby.")
                del clients[username]


def handle_packet(data: bytes, addr: tuple[str, int], sock: socket.socket):
    """Parse incoming UDP packets and route to the correct handler."""
    try:
        message = json.loads(data.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logging.warning(f"Received invalid JSON packet from {addr}")
        return

    cmd = message.get("cmd")
    username = message.get("username")
    
    if not cmd:
        return

    now = time.time()

    if cmd == "REGISTER":
        if not username:
            return
        
        with clients_lock:
            clients[username] = {
                "ip": addr[0],
                "port": addr[1],
                "last_seen": now,
                "state": "available"
            }
        logging.info(f"Registered/Updated client '{username}' at {addr}")
        
        # Acknowledge the registration
        response = json.dumps({"cmd": "REGISTER_ACK", "status": "ok"}).encode('utf-8')
        sock.sendto(response, addr)

    elif cmd == "KEEPALIVE":
        if not username:
            return
            
        with clients_lock:
            if username in clients:
                # Update last_seen and potentially IP/Port if NAT mapping fluctuated
                clients[username]["ip"] = addr[0]
                clients[username]["port"] = addr[1]
                clients[username]["last_seen"] = now
            else:
                # If they send keepalive but aren't registered, we can register them
                clients[username] = {
                    "ip": addr[0],
                    "port": addr[1],
                    "last_seen": now,
                    "state": "available"
                }
                logging.info(f"Auto-registered client '{username}' from KEEPALIVE at {addr}")

    elif cmd == "LIST_ONLINE":
        with clients_lock:
            # Exclude the requesting user from the response list if username is provided
            online_list = [
                {"username": uname, "state": cdata["state"]}
                for uname, cdata in clients.items()
                if uname != username
            ]
            
        response = json.dumps({
            "cmd": "ONLINE_LIST", 
            "players": online_list
        }).encode('utf-8')
        sock.sendto(response, addr)

    else:
        logging.debug(f"Unknown command '{cmd}' from {addr}")


def run_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((SERVER_HOST, SERVER_PORT))
    except Exception as e:
        logging.error(f"Failed to bind to {SERVER_HOST}:{SERVER_PORT} - {e}")
        return

    logging.info(f"UDP Matchmaking signaling server listening on {SERVER_HOST}:{SERVER_PORT}")

    # Start the garbage collection thread
    cleanup_thread = threading.Thread(target=cleanup_stale_clients, daemon=True)
    cleanup_thread.start()

    while True:
        try:
            data, addr = sock.recvfrom(4096)
            handle_packet(data, addr, sock)
        except Exception as e:
            logging.error(f"Error receiving UDP packet: {e}")


if __name__ == "__main__":
    run_server()