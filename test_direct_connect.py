#!/usr/bin/env python3
"""Direct test of internet match connection flow."""

import sys
import time
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from online_play.internet_session import InternetSessionClient


def _load_dotenv_token(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "GRID_SURVIVAL_ONLINE_API_KEY":
                    return value.strip().strip('"').strip("'")
    except OSError:
        return None
    return None

def main():
    client = InternetSessionClient()
    
    # Hardcoded server endpoint and token (from user's previous logs)
    endpoint = "38.242.246.126:5555"
    token = os.getenv("GRID_SURVIVAL_ONLINE_API_KEY") or _load_dotenv_token(
        os.path.join(os.path.dirname(__file__), ".env")
    ) or "test_token_12345"
    player_name = "TestPlayer"
    
    print(f"[TEST] Connecting to {endpoint} with token={token}, player={player_name}")
    print(f"[TEST] Starting time: {time.time()}")
    
    start = time.time()
    try:
        result = client.connect_to_match(endpoint=endpoint, token=token, player_name=player_name)
    except Exception as e:
        print(f"[TEST] Exception during connect_to_match: {e}")
        result = False
    
    elapsed = time.time() - start
    print(f"[TEST] connect_to_match returned {result} after {elapsed:.2f}s")
    print(f"[TEST] Final error: {client.last_error}")
    print(f"[TEST] transport.connected={client.connected}")
    print(f"[TEST] transport._last_recv_time={getattr(client, '_last_recv_time', 'N/A')}")
    
    if not result:
        print(f"[TEST] Connection failed")
        sys.exit(1)
    
    # Keep running for a bit to see if disconnect happens
    print(f"[TEST] Connected, waiting 10 seconds...")
    for i in range(10):
        time.sleep(1)
        print(f"[TEST] Tick {i+1}: connected={client.connected}, queue_depth={client.message_queue.qsize()}")
        msgs = client.get_messages()
        for msg in msgs:
            print(f"[TEST]   -> received {msg.get('type')}")
    
    print(f"[TEST] Done")

if __name__ == "__main__":
    main()
