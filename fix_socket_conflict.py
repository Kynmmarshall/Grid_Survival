#!/usr/bin/env python3
"""Fix internet_session.py socket conflict by removing _setup_udp_socket calls."""

import re

# Read the current file
with open(r'c:\Users\kynm\Desktop\Grid_Survival\online_play\internet_session.py', 'r') as f:
    content = f.read()

# The old problematic PHASE 1 section
old_phase1 = r'''        # === PHASE 1: Try TCP handshake \(most reliable through firewalls\) ===
        print\(f"\[DEBUG\] \[PHASE 1\] Attempting TCP handshake to \{host\}:\{port\}..."\)
        try:
            if hasattr\(self, 'transport'\) and hasattr\(self\.transport, '_tcp_handshake'\):
                if self\.transport\._tcp_handshake\(host, port, token, player_name\):
                    print\(f"\[DEBUG\] \[PHASE 1\] TCP auth succeeded!"\)
                    self\.session_id = self\.transport\.session_id
                    self\._last_auth_ok = True
                    
                    # Now set up UDP socket for game data
                    # \(no need to wait for hello_ack since TCP already authenticated\)
                    print\(f"\[DEBUG\] \[PHASE 1\] Setting up UDP socket for game data..."\)
                    if hasattr\(self\.transport, '_setup_udp_socket'\):
                        if self\.transport\._setup_udp_socket\(host, port\):
                            self\.transport\.connected = True
                            self\.transport\.udp_connected = True
                            self\.transport\._last_recv_time = time\.time\(\)
                            print\(f"\[DEBUG\] \[PHASE 1\] SUCCESS: Connected via TCP \+ UDP!"\)
                            return True
                        else:
                            print\(f"\[DEBUG\] \[PHASE 1\] UDP setup failed: \{self\.transport\.last_error\}"\)
                    else:
                        print\(f"\[DEBUG\] \[PHASE 1\] _setup_udp_socket not available"\)
        except Exception as e:
            try:
                print\(f"\[DEBUG\] \[PHASE 1\] TCP auth exception: \{e\}"\)
            except Exception:
                pass

        # === PHASE 2: Fallback to UDP hello \(backward compatibility\) ===
        print\(f"\[DEBUG\] \[PHASE 2\] TCP failed, trying UDP hello..."\)'''

# The new PHASE 1 & 2
new_phase1 = '''        # === PHASE 1: Try TCP handshake (most reliable through firewalls) ===
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
        print(f"[DEBUG] [PHASE 2] Trying fresh UDP hello...")'''

# Try simple string replacement instead of regex
if "# Now set up UDP socket for game data" in content:
    print("Found old code with _setup_udp_socket")
    
    # Find the start and end of the PHASE 1/2 section
    start_idx = content.find("        # === PHASE 1: Try TCP handshake (most reliable through firewalls) ===")
    end_idx = content.find("        # === PHASE 2:", start_idx) 
    phase2_full_idx = content.find("        print(f\"[DEBUG] [PHASE 2] TCP failed, trying UDP hello...\")")
    phase2_new_idx = content.find("        print(f\"[DEBUG] [PHASE 2] Trying fresh UDP hello...\")")
    
    if start_idx != -1 and end_idx != -1:
        # Extract the old section
        old_section = content[start_idx:end_idx + len("        # === PHASE 2:")]
        print(f"Old section length: {len(old_section)}")
        print("Old section found. Replacing...")
        
        # Find exact end of PHASE 2 comment line
        phase2_comment_idx = content.find("        # === PHASE 2: Fallback to UDP hello (backward compatibility) ===", start_idx)
        phase2_print_idx = content.find("        print(f\"[DEBUG] [PHASE 2] TCP failed, trying UDP hello...\")", start_idx)
        
        if phase2_comment_idx != -1 and phase2_print_idx != -1:
            # Build the replacement
            before = content[:start_idx]
            old_phase2_comment = content[phase2_comment_idx:phase2_print_idx + len("        print(f\"[DEBUG] [PHASE 2] TCP failed, trying UDP hello...\")")]
            after = content[phase2_print_idx + len("        print(f\"[DEBUG] [PHASE 2] TCP failed, trying UDP hello...\")") - 1:]
            
            # Replace the old comment and print with new version
            replacement = new_phase1.rstrip() + "\n"
            replacement += "        print(f\"[DEBUG] [PHASE 2] Trying fresh UDP hello...\")"
            
            new_content = before + replacement + after
            
            with open(r'c:\Users\kynm\Desktop\Grid_Survival\online_play\internet_session.py', 'w') as f:
                f.write(new_content)
            print("✓ File updated successfully!")
        else:
            print("Could not find PHASE 2 markers")
else:
    print("Old code not found. File may already be fixed or structure changed.")
    # Check if new code is already there
    if "tcp_auth_ok = False" in content:
        print("✓ File appears to already have the fix!")
    else:
        print("⚠ File doesn't match expected pattern. Manual review needed.")
