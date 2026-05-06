#!/usr/bin/env python3
"""Properly fix internet_session.py by replacing the connect_to_match method."""

import shutil

# Backup original
shutil.copy(
    r'c:\Users\kynm\Desktop\Grid_Survival\online_play\internet_session.py',
    r'c:\Users\kynm\Desktop\Grid_Survival\online_play\internet_session.py.backup'
)

# Read the entire file
with open(r'c:\Users\kynm\Desktop\Grid_Survival\online_play\internet_session.py', 'r') as f:
    content = f.read()

# The replacement method (PHASE 1 and PHASE 2 sections only)
phase1_replacement = '''        # === PHASE 1: Try TCP handshake (most reliable through firewalls) ===
        print(f"[DEBUG] [PHASE 1] Attempting TCP handshake to {host}:{port}...")
        tcp_auth_ok = False
        try:
            if hasattr(self, 'transport') and hasattr(self.transport, '_tcp_handshake'):
                if self.transport._tcp_handshake(host, port, token, player_name):
                    print(f"[DEBUG] [PHASE 1] TCP auth succeeded!")
                    self.session_id = self.transport.session_id
                    self._last_auth_ok = True
                    tcp_auth_ok = True
        except Exception as e:
            try:
                print(f"[DEBUG] [PHASE 1] TCP auth exception: {e}")
            except Exception:
                pass
        
        if tcp_auth_ok:
            print(f"[DEBUG] [PHASE 1] TCP ok, attempting UDP hello...")
            if self.connect_to_host(host, port):
                print(f"[DEBUG] [PHASE 1] SUCCESS: Connected via TCP auth + UDP hello!")
                return True
            else:
                print(f"[DEBUG] [PHASE 1] UDP hello failed: {self.last_error}")
        
        # === PHASE 2: Try clean UDP hello from scratch ===
        print(f"[DEBUG] [PHASE 2] Trying fresh UDP hello...")
        connected = False
        for attempt in range(1, 4):
            print(f"[DEBUG] [PHASE 2] UDP hello attempt {attempt}/3...")
            if self.connect_to_host(host, port):
                connected = True
                print(f"[DEBUG] [PHASE 2] UDP hello succeeded!")
                break
            print(f"[DEBUG] [PHASE 2] Attempt {attempt} failed: {self.last_error}")
            if attempt < 3:
                time.sleep(0.35)'''

# The old PHASE 1 and PHASE 2 sections to replace
old_phase1_start = '''        # === PHASE 1: Try TCP handshake (most reliable through firewalls) ===
        print(f"[DEBUG] [PHASE 1] Attempting TCP handshake to {host}:{port}...")
        try:
            if hasattr(self, 'transport') and hasattr(self.transport, '_tcp_handshake'):
                if self.transport._tcp_handshake(host, port, token, player_name):
                    print(f"[DEBUG] [PHASE 1] TCP auth succeeded!")
                    self.session_id = self.transport.session_id
                    self._last_auth_ok = True
                    
                    # Now set up UDP socket for game data
                    # (no need to wait for hello_ack since TCP already authenticated)
                    print(f"[DEBUG] [PHASE 1] Setting up UDP socket for game data...")
                    if hasattr(self.transport, '_setup_udp_socket'):
                        if self.transport._setup_udp_socket(host, port):
                            self.transport.connected = True
                            self.transport.udp_connected = True
                            self.transport._last_recv_time = time.time()
                            print(f"[DEBUG] [PHASE 1] SUCCESS: Connected via TCP + UDP!")
                            return True
                        else:
                            print(f"[DEBUG] [PHASE 1] UDP setup failed: {self.transport.last_error}")
                    else:
                        print(f"[DEBUG] [PHASE 1] _setup_udp_socket not available")
        except Exception as e:
            try:
                print(f"[DEBUG] [PHASE 1] TCP auth exception: {e}")
            except Exception:
                pass

        # === PHASE 2: Fallback to UDP hello (backward compatibility) ===
        print(f"[DEBUG] [PHASE 2] TCP failed, trying UDP hello...")
        connected = False
        for attempt in range(1, 4):
            print(f"[DEBUG] [PHASE 2] UDP hello attempt {attempt}/3...")
            if self.connect_to_host(host, port):
                connected = True
                print(f"[DEBUG] [PHASE 2] UDP hello succeeded!")
                break
            print(f"[DEBUG] [PHASE 2] Attempt {attempt} failed: {self.last_error}")
            if attempt < 3:
                time.sleep(0.35)'''

# Replace
if old_phase1_start in content:
    new_content = content.replace(old_phase1_start, phase1_replacement)
    with open(r'c:\Users\kynm\Desktop\Grid_Survival\online_play\internet_session.py', 'w') as f:
        f.write(new_content)
    print("✓ File fixed successfully!")
    print(f"  Backup saved to: online_play/internet_session.py.backup")
else:
    print("ERROR: Old phase text not found in file")
    print("File may have been modified or restored to a different state")
