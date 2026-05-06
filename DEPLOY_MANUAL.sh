#!/usr/bin/env bash
# Manual deployment commands for Grid Survival TCP+UDP changes

VPS_HOST="root@vmi2899245.contaboserver.com"
VPS_PATH="~/Grid_Survival"

echo "=== STEP 1: Copy files via SCP ==="
echo "Run these commands in your terminal:"
echo ""
echo "scp backend/match_daemon.py ${VPS_HOST}:${VPS_PATH}/backend/"
echo "scp online_play/transport.py ${VPS_HOST}:${VPS_PATH}/online_play/"
echo "scp online_play/internet_session.py ${VPS_HOST}:${VPS_PATH}/online_play/"
echo ""

echo "=== STEP 2: Verify files ==="
echo "ssh ${VPS_HOST} 'cd ${VPS_PATH} && python3 -m py_compile backend/match_daemon.py online_play/transport.py online_play/internet_session.py'"
echo ""

echo "=== STEP 3: Restart daemon ==="
echo "ssh ${VPS_HOST} 'sudo systemctl restart grid-survival-control'"
echo ""

echo "=== STEP 4: Check logs ==="
echo "ssh ${VPS_HOST} 'sudo journalctl -u grid-survival-control -n 20'"
