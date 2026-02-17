#!/usr/bin/env pwsh
# Stop script for AI-KYC application
# Stops all running backend and frontend instances

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "AI-KYC Application Stop" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Stop backend server (port 8087)
Write-Host "[1/2] Stopping backend server..." -ForegroundColor Yellow
$backendProcesses = Get-NetTCPConnection -LocalPort 8087 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess
if ($backendProcesses) {
    foreach ($processId in $backendProcesses) {
        try {
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
            Write-Host "  ✓ Stopped process $processId" -ForegroundColor Green
        }
        catch {
            Write-Host "  ! Could not stop process $processId" -ForegroundColor Yellow
        }
    }
}
else {
    Write-Host "  No backend processes running" -ForegroundColor Gray
}

# Stop frontend server (Node/Vite)
Write-Host ""
Write-Host "[2/2] Stopping frontend server..." -ForegroundColor Yellow
$nodeProcesses = Get-Process | Where-Object { $_.ProcessName -like "*node*" } -ErrorAction SilentlyContinue
if ($nodeProcesses) {
    $stoppedCount = 0
    foreach ($proc in $nodeProcesses) {
        try {
            # Check if it's a Vite process
            $cmdLine = (Get-CimInstance Win32_Process -Filter "ProcessId = $($proc.Id)" -ErrorAction SilentlyContinue).CommandLine
            if ($cmdLine -like "*vite*" -or $cmdLine -like "*npm*dev*") {
                Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
                Write-Host "  ✓ Stopped Node process $($proc.Id)" -ForegroundColor Green
                $stoppedCount++
            }
        }
        catch {
            # Ignore errors
        }
    }
    if ($stoppedCount -eq 0) {
        Write-Host "  No frontend processes found" -ForegroundColor Gray
    }
}
else {
    Write-Host "  No Node processes running" -ForegroundColor Gray
}

# Stop any background jobs
$jobs = Get-Job -ErrorAction SilentlyContinue
if ($jobs) {
    Write-Host ""
    Write-Host "Stopping background jobs..." -ForegroundColor Yellow
    foreach ($job in $jobs) {
        Stop-Job -Id $job.Id -ErrorAction SilentlyContinue
        Remove-Job -Id $job.Id -Force -ErrorAction SilentlyContinue
        Write-Host "  ✓ Stopped job $($job.Id)" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "✓ All services stopped" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
