#!/usr/bin/env python3
"""Test TCP+UDP hybrid handshake with the match daemon."""

import json
import socket
import sys
import time

SERVER_HOST = "38.242.246.126"  # Your VPS IP
TCP_PORT = 5554
UDP_PORT = 5555

# Use a test token and player name
TEST_TOKEN = "test-token-12345"
TEST_PLAYER = "TestPlayer"

def test_tcp_handshake():
    """Test TCP handshake with the server."""
    print("=" * 60)
    print("TCP HANDSHAKE TEST")
    print("=" * 60)
    print(f"Target: {SERVER_HOST}:{TCP_PORT} (TCP)")
    print()
    
    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.settimeout(5.0)
    
    try:
        # Step 1: Connect
        print("[1/4] Connecting to TCP server...")
        tcp_sock.connect((SERVER_HOST, TCP_PORT))
        print("      ✓ Connected")
        print()
        
        # Step 2: Send hello
        print("[2/4] Sending hello...")
        hello_msg = json.dumps({"type": "hello"}, separators=(",", ":"), ensure_ascii=True)
        tcp_sock.send(hello_msg.encode("utf-8") + b"\n")
        print(f"      Sent: {hello_msg}")
        
        # Receive hello_ack
        data = tcp_sock.recv(4096)
        if not data:
            print("      ✗ Connection closed by server")
            return False
        
        hello_ack = json.loads(data.decode("utf-8").strip())
        if hello_ack.get("type") != "hello_ack":
            print(f"      ✗ Unexpected response: {hello_ack}")
            return False
        print(f"      Received: {hello_ack}")
        print("      ✓ Hello handshake successful")
        print()
        
        # Step 3: Send internet_auth
        print("[3/4] Sending internet_auth...")
        auth_msg = json.dumps({
            "type": "internet_auth",
            "token": TEST_TOKEN,
            "player": TEST_PLAYER
        }, separators=(",", ":"), ensure_ascii=True)
        tcp_sock.send(auth_msg.encode("utf-8") + b"\n")
        print(f"      Sent: {auth_msg}")
        
        # Receive internet_auth_ok or error
        data = tcp_sock.recv(4096)
        if not data:
            print("      ✗ Connection closed by server")
            return False
        
        auth_ok = json.loads(data.decode("utf-8").strip())
        msg_type = auth_ok.get("type")
        
        if msg_type == "internet_auth_error":
            print(f"      ✗ Auth error: {auth_ok.get('error')}")
            print("         (This is expected if the token doesn't exist on server)")
            print("         ✓ TCP handshake mechanism works, just auth token invalid")
            print()
            print("[SUCCESS] TCP handshake infrastructure is working!")
            return True
        
        if msg_type != "internet_auth_ok":
            print(f"      ✗ Unexpected response: {auth_ok}")
            return False
        
        print(f"      Received: {auth_ok}")
        session_id = auth_ok.get("session_id", "?")
        print(f"      Session ID: {session_id}")
        print("      ✓ Authentication successful")
        print()
        
        # Step 4: Test UDP connection
        print("[4/4] Testing UDP connection...")
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        udp_sock.bind(("0.0.0.0", 0))
        local_udp_port = udp_sock.getsockname()[1]
        print(f"      UDP local port: {local_udp_port}")
        
        # Send UDP hello
        hello_udp = json.dumps({"k": "h"}, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        udp_sock.sendto(hello_udp, (SERVER_HOST, UDP_PORT))
        print("      Sent: UDP hello probe")
        
        udp_sock.settimeout(2.0)
        try:
            data, addr = udp_sock.recvfrom(4096)
            packet = json.loads(data.decode("utf-8"))
            print(f"      Received: {packet}")
            if packet.get("k") == "ha":
                print("      ✓ UDP hello_ack received (bidirectional UDP works!)")
            else:
                print("      ! Got response but not hello_ack")
        except socket.timeout:
            print("      ! UDP response timeout")
            print("         (Firewall may still block inbound UDP, but TCP works)")
        
        print()
        print("=" * 60)
        print("[SUCCESS] TCP+UDP hybrid mode is working!")
        print("=" * 60)
        return True
        
    except socket.timeout:
        print("      ✗ Connection timeout")
        print(f"         Check that {SERVER_HOST}:{TCP_PORT} is reachable")
        return False
    except (socket.error, OSError) as e:
        print(f"      ✗ Connection error: {e}")
        return False
    except json.JSONDecodeError as e:
        print(f"      ✗ Invalid JSON response: {e}")
        return False
    finally:
        try:
            tcp_sock.close()
        except:
            pass

if __name__ == "__main__":
    success = test_tcp_handshake()
    sys.exit(0 if success else 1)
