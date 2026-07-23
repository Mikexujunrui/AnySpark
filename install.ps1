# AnySpark 一键部署脚本 (Windows PowerShell)
# 用法：在项目根目录右键 → "用 PowerShell 运行"，或执行：powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$projectDir = $PSScriptRoot
Set-Location $projectDir

function Write-Step($msg) { Write-Host $msg -ForegroundColor White }
function Write-Ok($msg)   { Write-Host "  ✓ $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  ℹ $msg" -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host "  ✗ $msg" -ForegroundColor Red }

Write-Host "===========================================" -ForegroundColor Green
Write-Host "  AnySpark 一键部署" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green

# ── 1. 检测 Docker ──
Write-Host ""
Write-Step "[1/5] 检测 Docker..."
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Err "Docker 未安装！"
    Write-Host "  请先安装 Docker Desktop: https://docs.docker.com/desktop/install/windows-install/"
    exit 1
}
Write-Ok "Docker 已安装"

# ── 2. 检测 Docker 服务 ──
Write-Host ""
Write-Step "[2/5] 检测 Docker 服务..."
docker info 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Err "Docker 服务未运行！"
    Write-Host "  请启动 Docker Desktop 后重试"
    exit 1
}
Write-Ok "Docker 服务运行中"

# ── 3. 配置 .env ──
Write-Host ""
Write-Step "[3/5] 配置环境变量..."
if (Test-Path .env) {
    Write-Warn "已存在 .env，跳过配置"
} else {
    Write-Host "  首次运行，需要配置："
    $apiKey = Read-Host "  请输入 DeepSeek API Key (必填)"
    if ([string]::IsNullOrWhiteSpace($apiKey)) {
        Write-Err "API Key 不能为空"
        exit 1
    }
    $neo4jPass = Read-Host "  Neo4j 密码 (直接回车用默认)"
    if ([string]::IsNullOrWhiteSpace($neo4jPass)) {
        $neo4jPass = "novel_agent_2024!"
    }

    $envContent = @"
DEEPSEEK_API_KEY=$apiKey
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
LLM_MODE=split
NEO4J_PASSWORD=$neo4jPass
SERVER_PORT=8191
"@
    # 用 UTF8NoBOM 写入，避免 docker compose 解析 BOM 出问题
    [System.IO.File]::WriteAllText("$projectDir\.env", $envContent, [System.Text.UTF8Encoding]::new($false))
    Write-Ok ".env 已生成"
}

# ── 4. 拉取镜像 + 启动 ──
Write-Host ""
Write-Step "[4/5] 拉取镜像并启动..."
New-Item -ItemType Directory -Force -Path data | Out-Null
docker compose pull
if ($LASTEXITCODE -ne 0) { Write-Err "镜像拉取失败"; exit 1 }
docker compose up -d
if ($LASTEXITCODE -ne 0) { Write-Err "启动失败"; exit 1 }

# ── 5. 等待服务就绪 ──
Write-Host ""
Write-Step "[5/5] 等待服务就绪..."
$ready = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        Invoke-WebRequest -Uri "http://localhost:8190" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop | Out-Null
        Write-Ok "前端已就绪"
        $ready = $true
        break
    } catch {
        Write-Host "  等待中... ($i/30)"
        Start-Sleep -Seconds 3
    }
}

if (-not $ready) {
    Write-Warn "服务仍在启动中，请稍后访问"
    Write-Host "  查看日志：docker compose logs -f"
}

Write-Host ""
Write-Host "===========================================" -ForegroundColor Green
Write-Host "  部署完成！" -ForegroundColor Green
Write-Host "===========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  访问地址：    http://localhost:8190"
Write-Host "  Neo4j 控制台：http://localhost:7474"
Write-Host ""
Write-Host "  常用命令："
Write-Host "    停止：    docker compose down"
Write-Host "    重启：    docker compose restart"
Write-Host "    查看日志：docker compose logs -f"
Write-Host "    更新版本：docker compose pull && docker compose up -d"
Write-Host ""
