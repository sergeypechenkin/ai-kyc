#!/usr/bin/env pwsh
# Quick test script to verify MAF agent tracing
# Usage: ./quick_test_tracing.ps1

Write-Host "======================================" -ForegroundColor Cyan
Write-Host "MAF Agent Tracing Quick Test" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Validate configuration
Write-Host "[1/4] Validating tracing configuration..." -ForegroundColor Yellow
python test_tracing.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Configuration validation failed. Fix errors above and retry." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[2/4] Starting MAF server (background)..." -ForegroundColor Yellow
$serverJob = Start-Job -ScriptBlock {
    Set-Location $using:PWD
    python -m src.maf.server --port 8087 2>&1
}

# Wait for server to start
Write-Host "Waiting for server to initialize..."
Start-Sleep -Seconds 5

# Check if server is running
$serverRunning = $false
for ($i = 0; $i -lt 10; $i++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8087/health" -Method GET -TimeoutSec 2 -UseBasicParsing 2>$null
        if ($response.StatusCode -eq 200) {
            $serverRunning = $true
            Write-Host "✅ Server is running!" -ForegroundColor Green
            break
        }
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $serverRunning) {
    Write-Host "❌ Server failed to start. Check output above." -ForegroundColor Red
    Stop-Job $serverJob
    Remove-Job $serverJob
    exit 1
}

Write-Host ""
Write-Host "[3/4] Sending test requests..." -ForegroundColor Yellow

# Test customer agent
Write-Host "  → Testing customer agent..."
try {
    $body = @{
        message = "I want to open a business account"
        role    = "customer"
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "http://localhost:8087/api/chat" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 30

    Write-Host "  ✅ Customer agent response received" -ForegroundColor Green
}
catch {
    Write-Host "  ❌ Customer agent request failed: $($_.Exception.Message)" -ForegroundColor Red
}

Start-Sleep -Seconds 2

# Test employee agent
Write-Host "  → Testing employee agent..."
try {
    $body = @{
        message = "Show me pending verifications"
        role    = "employee"
    } | ConvertTo-Json

    $response = Invoke-RestMethod -Uri "http://localhost:8087/api/chat" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 30

    Write-Host "  ✅ Employee agent response received" -ForegroundColor Green
}
catch {
    Write-Host "  ❌ Employee agent request failed: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "[4/4] Cleaning up..." -ForegroundColor Yellow
Stop-Job $serverJob
Remove-Job $serverJob

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "✅ Test completed!" -ForegroundColor Green
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. View traces in Azure Portal:" -ForegroundColor White
Write-Host "     Application Insights → Live Metrics (real-time)" -ForegroundColor Gray
Write-Host "     Application Insights → Transaction search (2-3 min delay)" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Run KQL queries in Logs:" -ForegroundColor White
Write-Host "     traces | where customDimensions.SpanName startswith `"agent.`"" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Check Application Map:" -ForegroundColor White
Write-Host "     Application Insights → Application map" -ForegroundColor Gray
Write-Host ""
Write-Host "  📖 Full guide: docs/TRACING_AND_MONITORING.md" -ForegroundColor Cyan
Write-Host ""
