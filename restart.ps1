#!/usr/bin/env pwsh
# Restart script for AI-KYC application
# Stops all running instances and starts fresh backend + frontend

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "AI-KYC Application Restart" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Stop all Python processes on port 8087
Write-Host "[1/4] Stopping backend server..." -ForegroundColor Yellow
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

# Step 2: Stop all Node/Vite processes (frontend)
Write-Host ""
Write-Host "[2/4] Stopping frontend server..." -ForegroundColor Yellow
$nodeProcesses = Get-Process | Where-Object { $_.ProcessName -like "*node*" -and $_.CommandLine -like "*vite*" } -ErrorAction SilentlyContinue
if ($nodeProcesses) {
    foreach ($proc in $nodeProcesses) {
        try {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  ✓ Stopped Node process $($proc.Id)" -ForegroundColor Green
        }
        catch {
            Write-Host "  ! Could not stop process $($proc.Id)" -ForegroundColor Yellow
        }
    }
}
else {
    Write-Host "  No frontend processes running" -ForegroundColor Gray
}

# Wait for processes to fully terminate
Write-Host ""
Write-Host "Waiting for processes to terminate..." -ForegroundColor Gray
Start-Sleep -Seconds 3

# Step 3: Start backend server
Write-Host ""
Write-Host "[3/4] Starting backend server..." -ForegroundColor Yellow
$backendJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    python -m src.maf.server --port 8087 2>&1
}

# Wait for backend to initialize
Write-Host "Waiting for backend to start..."
$backendReady = $false
for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8087/health" -Method GET -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $backendReady = $true
            Write-Host "  ✓ Backend is ready!" -ForegroundColor Green
            break
        }
    }
    catch {
        # Still starting...
    }
}

if (-not $backendReady) {
    Write-Host "  ⚠ Backend did not respond within 20 seconds" -ForegroundColor Yellow
    Write-Host "  Check for errors with: Receive-Job $($backendJob.Id)" -ForegroundColor Yellow
}

# Step 4: Start frontend server
Write-Host ""
Write-Host "[4/4] Starting frontend server..." -ForegroundColor Yellow
$frontendJob = Start-Job -ScriptBlock {
    Set-Location "$using:PWD\web"
    npm run dev 2>&1
}

# Wait for frontend to start
Write-Host "Waiting for frontend to start..."
Start-Sleep -Seconds 5

$frontendReady = $false
for ($i = 0; $i -lt 10; $i++) {
    Start-Sleep -Seconds 1
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:5173" -Method GET -TimeoutSec 2 -UseBasicParsing -ErrorAction SilentlyContinue
        if ($response.StatusCode -eq 200) {
            $frontendReady = $true
            Write-Host "  ✓ Frontend is ready!" -ForegroundColor Green
            break
        }
    }
    catch {
        # Still starting...
    }
}

if (-not $frontendReady) {
    Write-Host "  ⚠ Frontend did not respond within 10 seconds" -ForegroundColor Yellow
}

# Summary
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "✓ Application Restarted" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Services:" -ForegroundColor White
if ($backendReady) {
    Write-Host "  Backend:  http://localhost:8087  ✓" -ForegroundColor Green
} else {
    Write-Host "  Backend:  http://localhost:8087  ⚠" -ForegroundColor Yellow
}
if ($frontendReady) {
    Write-Host "  Frontend: http://localhost:5173  ✓" -ForegroundColor Green
} else {
    Write-Host "  Frontend: http://localhost:5173  ⚠" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Background Jobs:" -ForegroundColor White
Write-Host "  Backend Job ID:  $($backendJob.Id)" -ForegroundColor Gray
Write-Host "  Frontend Job ID: $($frontendJob.Id)" -ForegroundColor Gray
Write-Host ""
Write-Host "To view logs:" -ForegroundColor Yellow
Write-Host "  Backend:  Receive-Job $($backendJob.Id) -Keep" -ForegroundColor Gray
Write-Host "  Frontend: Receive-Job $($frontendJob.Id) -Keep" -ForegroundColor Gray
Write-Host ""
Write-Host "To stop jobs:" -ForegroundColor Yellow
Write-Host "  Stop-Job $($backendJob.Id),$($frontendJob.Id); Remove-Job $($backendJob.Id),$($frontendJob.Id)" -ForegroundColor Gray
Write-Host ""
Write-Host "Open application: http://localhost:5173" -ForegroundColor Cyan
Write-Host ""
