#!/usr/bin/env python3
"""
Debug script to trace exactly what's happening in the network flow.
Run this while the game is connecting to see detailed logs.
"""

import sys
import logging

# Set up detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(levelname)s] %(name)s - %(message)s'
)

# Import network modules with detailed logging
from online_play.transport import UdpClientTransport
import time

def test_connection_flow():
    print("\n" + "="*70)
    print("NETWORK CONNECTION DEBUG TRACE")
    print("="*70)
    
    # Test parameters (same as game)
    host = "38.242.246.126"
    port = 5555
    token = "test-token-12345"
    player_name = "DebugPlayer"
    
    print(f"\n[CONFIG] Target: {host}:{port}")
    print(f"[CONFIG] Token: {token}")
    print(f"[CONFIG] Player: {player_name}\n")
    
    # Create transport
    print("[1/3] Creating UDP transport...")
    transport = UdpClientTransport()
    print(f"      Created: {transport}")
    print(f"      Has _tcp_handshake: {hasattr(transport, '_tcp_handshake')}")
    print(f"      Has _setup_udp_socket: {hasattr(transport, '_setup_udp_socket')}")
    
    # Test UDP socket setup
    print("\n[2/3] Testing UDP socket setup...")
    try:
        if transport._setup_udp_socket(host, port):
            print(f"      ✓ UDP socket ready")
            print(f"      Socket: {transport.socket}")
            print(f"      Peer address: {transport.peer_address}")
        else:
            print(f"      ✗ UDP socket setup failed: {transport.last_error}")
            return
    except Exception as e:
        print(f"      ✗ Exception: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Test TCP handshake
    print("\n[3/3] Testing TCP handshake...")
    try:
        result = transport._tcp_handshake(host, port, token, player_name)
        print(f"      Result: {result}")
        print(f"      Session ID: {getattr(transport, 'session_id', 'NOT SET')}")
        print(f"      Auth token: {getattr(transport, 'tcp_auth_token', 'NOT SET')}")
    except Exception as e:
        print(f"      ✗ Exception: {e}")
        import traceback
        traceback.print_exc()
    
    # Check final state
    print("\n[FINAL STATE]")
    print(f"      connected: {transport.connected}")
    print(f"      udp_connected: {getattr(transport, 'udp_connected', 'NOT SET')}")
    print(f"      socket active: {transport.socket is not None}")
    print(f"      last_error: {transport.last_error}")
    
    # Try to receive a packet
    print("\n[LISTENING] Waiting for packets for 2 seconds...")
    start = time.time()
    packets = 0
    while time.time() - start < 2.0:
        try:
            msgs = transport.get_messages(timeout=0.1)
            if msgs:
                packets += len(msgs)
                for msg in msgs:
                    print(f"      ✓ Received: {msg}")
        except Exception as e:
            print(f"      Error: {e}")
            break
    
    if packets == 0:
        print(f"      ✗ No packets received in 2 seconds")
    else:
        print(f"      ✓ Received {packets} packets")

if __name__ == "__main__":
    test_connection_flow()
