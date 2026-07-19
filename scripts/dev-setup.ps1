# Dev Setup Script for Novel Writing Agent
# Requirements: Python 3.11+, Node 20+, Docker (for Neo4j)

param(
    [switch]$SkipNeo4j,
    [switch]$SkipPython,
    [switch]$SkipFrontend,
    [switch]$Help
)

if ($Help) {
    Write-Host @"
Novel Writing Agent - 开发环境搭建脚本
========================================

用法: .\scripts\dev-setup.ps1 [参数]

参数:
  -SkipNeo4j      跳过 Neo4j Docker 容器启动
  -SkipPython     跳过 Python 虚拟环境创建
  -SkipFrontend   跳过前端依赖安装
  -Help           显示此帮助信息

"@
    exit 0
}

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Novel Writing Agent - 开发环境搭建" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── Step 1: Check Prerequisites ──
Write-Host "[1/4] 检查系统环境..." -ForegroundColor Yellow

# Check Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  Python 未安装或不在 PATH 中！请安装 Python 3.11+" -ForegroundColor Red
    exit 1
}

# Check Node
try {
    $nodeVersion = node --version 2>&1
    Write-Host "  Node:    $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  Node.js 未安装或不在 PATH 中！请安装 Node 20+" -ForegroundColor Red
    exit 1
}

# Check Docker
if (-not $SkipNeo4j) {
    try {
        $dockerVersion = docker --version 2>&1
        Write-Host "  Docker:  $dockerVersion" -ForegroundColor Green
    } catch {
        Write-Host "  Docker 未安装！Neo4j 需要 Docker 运行。" -ForegroundColor Yellow
        Write-Host "  使用 -SkipNeo4j 参数跳过此步骤。" -ForegroundColor Yellow
    }
}

Write-Host ""

# ── Step 2: Start Neo4j ──
if (-not $SkipNeo4j) {
    Write-Host "[2/4] 启动 Neo4j 数据库..." -ForegroundColor Yellow
    try {
        $neo4jRunning = docker ps --filter "name=novel-neo4j" --format "{{.Names}}" 2>&1
        if ($neo4jRunning -match "novel-neo4j") {
            Write-Host "  Neo4j 容器已在运行" -ForegroundColor Green
        } else {
            Write-Host "  启动 Neo4j 容器..." -ForegroundColor Yellow
            docker compose -f "$projectRoot\docker-compose.yml" up -d neo4j
            Write-Host "  Neo4j 已启动 (端口 7474, 7687)" -ForegroundColor Green
            Write-Host "  等待 Neo4j 就绪..." -ForegroundColor Yellow
            Start-Sleep -Seconds 10
        }
    } catch {
        Write-Host "  Docker 未运行，跳过 Neo4j 启动" -ForegroundColor Yellow
    }
    Write-Host ""
}

# ── Step 3: Setup Python ──
if (-not $SkipPython) {
    Write-Host "[3/4] 配置 Python 环境..." -ForegroundColor Yellow

    $venvPath = "$projectRoot\.venv"
    if (-not (Test-Path $venvPath)) {
        Write-Host "  创建虚拟环境..." -ForegroundColor Yellow
        python -m venv $venvPath
    } else {
        Write-Host "  虚拟环境已存在" -ForegroundColor Green
    }

    # Activate and install
    $activatePath = "$venvPath\Scripts\Activate.ps1"
    if (Test-Path $activatePath) {
        & $activatePath
        Write-Host "  安装 Python 依赖..." -ForegroundColor Yellow
        pip install -r "$projectRoot\requirements.txt" -q
        pip install -r "$projectRoot\requirements-dev.txt" -q 2>$null
        Write-Host "  Python 依赖安装完成" -ForegroundColor Green
    }

    # Check .env
    $envPath = "$projectRoot\.env"
    if (-not (Test-Path $envPath)) {
        Write-Host "  创建 .env 文件..." -ForegroundColor Yellow
        Copy-Item "$projectRoot\.env.example" $envPath -ErrorAction SilentlyContinue
        if (-not (Test-Path $envPath)) {
            @"
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=novel_agent_2024!
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
"@ | Out-File -FilePath $envPath -Encoding utf8
        }
        Write-Host "  请编辑 .env 文件，填入你的 API Key" -ForegroundColor Yellow
    }

    Write-Host ""
}

# ── Step 4: Setup Frontend ──
if (-not $SkipFrontend) {
    Write-Host "[4/4] 配置前端环境..." -ForegroundColor Yellow

    $frontendPath = "$projectRoot\frontend"
    Set-Location $frontendPath
    Write-Host "  安装前端依赖..." -ForegroundColor Yellow
    npm install
    Write-Host "  前端依赖安装完成" -ForegroundColor Green
    Set-Location $projectRoot

    Write-Host ""
}

# ── Done ──
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  开发环境搭建完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "启动开发服务器:" -ForegroundColor White
Write-Host "  后端:  cd src && python -m uvicorn main:app --reload --port 8191" -ForegroundColor Gray
Write-Host "  前端:  cd frontend && npm run dev" -ForegroundColor Gray
Write-Host ""
Write-Host "或使用: .\start.ps1 一键启动" -ForegroundColor Gray
Write-Host ""
