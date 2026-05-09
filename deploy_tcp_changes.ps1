# PowerShell deployment script for TCP+UDP changes to VPS

$VpsHost = "root@vmi2899245.contaboserver.com"
$VpsPath = "~/Grid_Survival"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "DEPLOYING TCP+UDP CHANGES TO VPS" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# File list
$filesToSync = @(
    "backend/match_daemon.py",
    "online_play/transport.py",
    "online_play/internet_session.py"
)

Write-Host "[STEP 1] Copy files via SCP" -ForegroundColor Yellow
Write-Host ""

foreach ($file in $filesToSync) {
    $remotePath = "${VpsHost}:${VpsPath}/$file"
    Write-Host "Copying: $file"
    Write-Host "Command: scp `"$file`" `"$remotePath`""
    
    & scp $file $remotePath
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✓ Uploaded: $file" -ForegroundColor Green
    } else {
        Write-Host "✗ Failed to upload: $file" -ForegroundColor Red
        exit 1
    }
    Write-Host ""
}

Write-Host "[STEP 2] Verify files on server" -ForegroundColor Yellow
$checkCmd = "cd $VpsPath && python3 -m py_compile " + ($filesToSync -join " ")
Write-Host "Running syntax check on server..."
& ssh $VpsHost $checkCmd
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ All files syntax OK" -ForegroundColor Green
} else {
    Write-Host "✗ Syntax error on server" -ForegroundColor Red
    exit 1
}
Write-Host ""

Write-Host "[STEP 3] Restart match daemon" -ForegroundColor Yellow
Write-Host "Restarting grid-survival-control service..."
& ssh $VpsHost "sudo systemctl restart grid-survival-control"
if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Daemon restart command sent" -ForegroundColor Green
} else {
    Write-Host "! May have failed - check manually" -ForegroundColor Yellow
}
Write-Host ""

Start-Sleep -Seconds 2

Write-Host "[STEP 4] Check daemon status" -ForegroundColor Yellow
& ssh $VpsHost "sudo systemctl status grid-survival-control | head -10"
Write-Host ""

Write-Host "========================================" -ForegroundColor Green
Write-Host "✓ DEPLOYMENT COMPLETE" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Run TCP test:  python test_tcp_handshake.py"
Write-Host "  2. View VPS logs: ssh root@vmi2899245.contaboserver.com 'sudo journalctl -u grid-survival-control -f'"
Write-Host "  3. Run the game:  python main.py"
Write-Host ""
