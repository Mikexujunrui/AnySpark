# AI Novel Writing Agent - One-Click Startup
$projectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectDir

Write-Host "==========================================="
Write-Host "   AI Novel Writing Agent"
Write-Host "==========================================="

# 1. Neo4j
Write-Host "[1/3] Neo4j..."
$neo = docker start novel-neo4j 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Creating Neo4j container..."
    $create = docker run -d --name novel-neo4j `
        -p 7474:7474 -p 7687:7687 `
        -e NEO4J_AUTH=neo4j/novel_agent_2024! `
        -e NEO4J_PLUGINS='[]' `
        neo4j:5.26-community 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ERROR: Failed to create Neo4j container. Is Docker running?" -ForegroundColor Red
        Write-Host "  知识库功能将不可用。请安装 Docker Desktop 后重试。"
    } else {
        Write-Host "  OK: Neo4j created and started on port 7687"
        Write-Host "  (首次启动需等待约30秒初始化)"
        Start-Sleep -Seconds 30
    }
} else {
    Write-Host "  OK: Neo4j on port 7687"
}

# 2. Backend (with auto-restart)
Write-Host "[2/3] Backend (port 8191)..."
Get-NetTCPConnection -LocalPort 8191 -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}

function Start-Backend {
    Start-Process -FilePath "python" -ArgumentList "-u src/server.py" -PassThru
}
$backendProc = Start-Backend
Start-Sleep -Seconds 4

# 3. Frontend
Write-Host "[3/3] Frontend (port 8190)..."
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