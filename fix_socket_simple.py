#!/usr/bin/env python3
"""Fix socket conflict by removing _setup_udp_socket and simplifying connect_to_match flow."""

# Read file
with open(r'c:\Users\kynm\Desktop\Grid_Survival\online_play\internet_session.py', 'r') as f:
    lines = f.readlines()

# Find the lines to modify (looking for _setup_udp_socket call)
output = []
skip_mode = False
i = 0

while i < len(lines):
    line = lines[i]
    
    # Check if we're at the "Now set up UDP socket" comment - start of problematic section
    if "# Now set up UDP socket for game data" in line:
        # We need to skip from here until we find the next non-indented block
        # This includes the _setup_udp_socket call and the failed return
        print(f"Found problematic section at line {i+1}")
        
        # Skip the UDP setup block (multiple lines)
        indent = len(line) - len(line.lstrip())
        i += 1
        
        while i < len(lines):
            next_line = lines[i]
            next_indent = len(next_line) - len(next_line.lstrip()) if next_line.strip() else indent
            
            # If we hit a line at the same indent level that's not part of this block, stop
            if next_line.strip() and next_indent <= indent and "except Exception as e:" not in next_line:
                break
            i += 1
        
        # Now add the simplified version
        output.append("                    tcp_auth_ok = True\n")
        output.append("        except Exception as e:\n")
        output.append("            try:\n")
        output.append("                print(f\"[DEBUG] [PHASE 1] TCP auth exception: {e}\")\n")
        output.append("            except Exception:\n")
        output.append("                pass\n")
        output.append("        \n")
        output.append("        if tcp_auth_ok:\n")
        output.append("            print(f\"[DEBUG] [PHASE 1] TCP ok, attempting UDP hello...\")\n")
        output.append("            if self.connect_to_host(host, port):\n")
        output.append("                print(f\"[DEBUG] [PHASE 1] SUCCESS: Connected via TCP auth + UDP hello!\")\n")
        output.append("                return True\n")
        output.append("            else:\n")
        output.append("                print(f\"[DEBUG] [PHASE 1] UDP hello failed: {self.last_error}\")\n")
        output.append("        \n")
        output.append("        # === PHASE 2: Try clean UDP hello from scratch ===\n")
        output.append("        print(f\"[DEBUG] [PHASE 2] Trying fresh UDP hello...\")\n")
        
        # Skip the old "PHASE 2" comment and print statement
        while i < len(lines) and "# === PHASE 2: Fallback to UDP hello" not in lines[i]:
            i += 1
        i += 1  # skip the comment line
        if i < len(lines) and "print(f\"[DEBUG] [PHASE 2] TCP failed" in lines[i]:
            i += 1  # skip the print line
        
        continue
    
    output.append(line)
    i += 1

# Write the fixed file
with open(r'c:\Users\kynm\Desktop\Grid_Survival\online_play\internet_session.py', 'w') as f:
    f.writelines(output)

print("✓ File fixed successfully!")
