#!/usr/bin/env python3
"""Deploy changes to VPS and restart daemon."""

import subprocess
import sys
import os

VPS_HOST = "root@vmi2899245.contaboserver.com"
VPS_PATH = "~/Grid_Survival"

def run_command(cmd, description=None, check=True):
    """Run a command and return the result."""
    if description:
        print(f"\n[*] {description}...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=check)
        if description:
            print(f"    ✓ {description}")
        return result
    except subprocess.TimeoutExpired:
        print(f"    ✗ Timeout: {description}")
        return None
    except subprocess.CalledProcessError as e:
        if check:
            print(f"    ✗ Failed: {description}")
            if e.stderr:
                print(f"    Error: {e.stderr}")
        return e
    except Exception as e:
        print(f"    ✗ Error: {e}")
        return None

def deploy():
    """Deploy the changes to VPS."""
    print("=" * 70)
    print("DEPLOYING TCP+UDP HYBRID IMPLEMENTATION TO VPS")
    print("=" * 70)
    
    # Check if we have SSH access
    print("\n[1/5] Checking SSH connection...")
    test_ssh = run_command(
        ["ssh", "-o", "ConnectTimeout=5", VPS_HOST, "echo", "SSH OK"],
        "SSH connectivity",
        check=False
    )
    if not test_ssh or test_ssh.returncode != 0:
        print("    ✗ Cannot reach VPS via SSH")
        print("    Make sure you have SSH access configured")
        return False
    
    # Copy modified files
    files_to_sync = [
        "backend/match_daemon.py",
        "online_play/transport.py",
        "online_play/internet_session.py",
    ]
    
    print("\n[2/5] Syncing Python files to VPS...")
    for file_path in files_to_sync:
        local_path = file_path
        remote_path = f"{VPS_HOST}:{VPS_PATH}/{file_path}"
        
        result = run_command(
            ["scp", local_path, remote_path],
            f"Upload {file_path}",
            check=False
        )
        if result and result.returncode != 0:
            print(f"    ✗ Failed to upload {file_path}")
            print(f"    {result.stderr if result.stderr else 'Unknown error'}")
            return False
    
    # Verify files on server
    print("\n[3/5] Verifying files on server...")
    for file_path in files_to_sync:
        result = run_command(
            ["ssh", VPS_HOST, "test", "-f", f"{VPS_PATH}/{file_path}"],
            f"Check {file_path}",
            check=False
        )
        if result and result.returncode != 0:
            print(f"    ✗ File not found on server: {file_path}")
            return False
    
    # Syntax check on server
    print("\n[4/5] Syntax checking on server...")
    check_cmd = " && ".join([f"python3 -m py_compile {VPS_PATH}/{f}" for f in files_to_sync])
    result = run_command(
        ["ssh", VPS_HOST, check_cmd],
        "Compile check",
        check=False
    )
    if result and result.returncode != 0:
        print(f"    ✗ Syntax error on server")
        print(f"    {result.stderr if result.stderr else 'Unknown error'}")
        return False
    
    # Restart daemon
    print("\n[5/5] Restarting match daemon...")
    result = run_command(
        ["ssh", VPS_HOST, "sudo systemctl restart grid-survival-control"],
        "Restart daemon",
        check=False
    )
    if result and result.returncode != 0:
        print(f"    ✗ Failed to restart daemon")
        if "sudo" in result.stderr.lower():
            print("    (Try running: ssh root@vmi2899245.contaboserver.com sudo systemctl restart grid-survival-control)")
        return False
    
    # Wait for daemon to start
    print("\n[6/6] Waiting for daemon to start...")
    import time
    time.sleep(2)
    
    # Check daemon status
    result = run_command(
        ["ssh", VPS_HOST, "sudo systemctl status grid-survival-control"],
        "Check daemon status",
        check=False
    )
    if result and result.returncode == 0:
        print("    ✓ Daemon is running")
    else:
        print("    ! Could not verify daemon status (check manually)")
    
    print("\n" + "=" * 70)
    print("✓ DEPLOYMENT COMPLETE!")
    print("=" * 70)
    print("\nNext steps:")
    print("  1. Run the TCP test: python test_tcp_handshake.py")
    print("  2. Check VPS logs:  ssh root@vmi2899245.contaboserver.com sudo journalctl -u grid-survival-control -f")
    print("  3. Run the game:    python main.py")
    print()
    
    return True

if __name__ == "__main__":
    success = deploy()
    sys.exit(0 if success else 1)
