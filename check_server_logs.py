#!/usr/bin/env python3
"""SSH into VPS and check recent daemon logs to see if hello_ack was sent."""

import subprocess
import sys

# SSH and check logs
cmd = [
    "ssh", 
    "root@vmi2899245.contaboserver.com",
    "sudo journalctl -u grid-survival-control -n 50 | grep -E '\\[SEND\\]|\\[NET\\]|session'"
]

print("Retrieving server logs for send attempts...")
print()

try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
except subprocess.TimeoutExpired:
    print("SSH timed out")
except Exception as e:
    print(f"Error: {e}")
