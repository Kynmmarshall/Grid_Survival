#!/usr/bin/env python3
"""Minimal test to identify what's calling _mark_disconnected."""

import sys
import time
import os

sys.path.insert(0, os.path.dirname(__file__))

from online_play.internet_session import InternetSessionClient

def main():
    client = InternetSessionClient()
    # For this minimal test, point the transport attribute at the client
    # so _tcp_handshake() is available (production code sets transport separately).
    client.transport = client
    
    endpoint = "38.242.246.126:5555"
    # Prefer token from environment for secure runs; fall back to test token
    token = os.getenv("GRID_SURVIVAL_ONLINE_API_KEY", "test_token_12345")
    player_name = "kynmmarshall"
    
    print(f"[TEST] Connecting to {endpoint}")
    
    start = time.time()
    result = client.connect_to_match(endpoint=endpoint, token=token, player_name=player_name)
    elapsed = time.time() - start
    
    print(f"[TEST] Result: {result} in {elapsed:.2f}s")
    
    if result:
        print(f"[TEST] Connected! Monitoring for 20 seconds...")
        for i in range(20):
            time.sleep(1)
            status = "CONNECTED" if client.connected else "DISCONNECTED"
            print(f"[TEST] {i+1}s: {status}")
            if not client.connected:
                print(f"[TEST] Disconnected at {i+1}s!")
                break

if __name__ == "__main__":
    main()
