# AI Novel Writing Agent - One-Click Startup
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

Write-Host "==========================================="
Write-Host "   AI Novel Writing Agent"
Write-Host "==========================================="

# 1. Backend (with auto-restart)
Write-Host "[1/2] Backend (port 8191)..."
Get-NetTCPConnection -LocalPort 8191 -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}

function Start-Backend {
    Start-Process -FilePath "python" -ArgumentList "-u src/server.py" -PassThru
}
$backendProc = Start-Backend
Start-Sleep -Seconds 4

# 2. Frontend
Write-Host "[2/2] Frontend (port 8190)..."
Start-Process -FilePath "cmd" -ArgumentList "/c cd /d `"$projectDir\frontend`" && npx vite --port 8190 --host"
Start-Sleep -Seconds 4

# 4. Open browser
Write-Host ""
Write-Host "  Opening: http://localhost:8190"
Start-Process "http://localhost:8190"
Write-Host ""

# Health check loop (every 30s restart backend if died, max 3 restarts)
$restarts = 0
$maxRestarts = 3
$healthOkMsg = "[health] backend OK"
$healthDownMsg = "[health] backend DOWN, restarting"
$healthMaxMsg = "[health] max restarts reached"
$healthDoneMsg = "[health] monitoring stopped after $maxRestarts restarts."
while ($restarts -lt $maxRestarts) {
    Start-Sleep -Seconds 30
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:8191/api/mode" -TimeoutSec 3 -UseBasicParsing
        Write-Host $healthOkMsg -ForegroundColor DarkGray
    } catch {
        $restarts++
        if ($restarts -le $maxRestarts) {
            Write-Host ("$healthDownMsg (attempt $restarts/$maxRestarts)") -ForegroundColor Yellow
            if ($backendProc -and !$backendProc.HasExited) {
                Stop-Process -Id $backendProc.Id -Force -ErrorAction SilentlyContinue
            }
            Get-NetTCPConnection -LocalPort 8191 -ErrorAction SilentlyContinue | ForEach-Object {
                Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
            }
            $backendProc = Start-Backend
            Start-Sleep -Seconds 4
        } else {
            Write-Host $healthMaxMsg -ForegroundColor Red
        }
    }
}

Write-Host $healthDoneMsg -ForegroundColor DarkCyan
Read-Host "Press Enter to exit"