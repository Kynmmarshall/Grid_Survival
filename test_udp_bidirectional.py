#!/usr/bin/env python3
"""Test bidirectional UDP communication with the server."""

import socket
import json
import time
import sys

SERVER_HOST = "38.242.246.126"  # Your VPS IP
SERVER_PORT = 5555

def test_udp():
    """Test if we can send to server and receive responses back."""
    print(f"Testing UDP bidirectional communication with {SERVER_HOST}:{SERVER_PORT}")
    print()
    
    # Create UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 0))  # Bind to any available port
    local_port = sock.getsockname()[1]
    print(f"[INFO] Bound to local port {local_port}")
    
    sock.settimeout(2.0)  # 2 second timeout for receives
    
    # Test 1: Send hello probe
    print("\n[TEST 1] Sending hello probe...")
    hello_packet = {"k": "h"}
    hello_json = json.dumps(hello_packet, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    
    try:
        sock.sendto(hello_json, (SERVER_HOST, SERVER_PORT))
        print(f"[SENT] Hello probe ({len(hello_json)} bytes)")
    except Exception as e:
        print(f"[ERROR] Failed to send hello: {e}")
        sock.close()
        return
    
    # Wait for hello_ack
    print("[WAIT] Waiting for hello_ack response (timeout: 2s)...")
    try:
        data, addr = sock.recvfrom(4096)
        packet = json.loads(data.decode("utf-8"))
        print(f"[RECV] Got response from {addr}: {packet}")
        if packet.get("k") == "ha":
            print("[SUCCESS] Received hello_ack! UDP is bidirectional.")
        else:
            print(f"[UNEXPECTED] Got {packet.get('k')}, expected 'ha'")
    except socket.timeout:
        print("[TIMEOUT] No response received after 2s - UDP is UNIDIRECTIONAL!")
        print("         The server likely CAN'T send responses back to your local port.")
        print("         This could be a Windows firewall or ISP blocking inbound UDP.")
    except Exception as e:
        print(f"[ERROR] Failed to receive: {e}")
    
    sock.close()

if __name__ == "__main__":
    test_udp()
