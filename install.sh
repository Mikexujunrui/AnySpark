#!/usr/bin/env bash
# AnySpark 一键部署脚本 (Linux / macOS)
# 用法：bash install.sh
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

projectDir="$(cd "$(dirname "$0")" && pwd)"
cd "$projectDir"

echo -e "${GREEN}===========================================${NC}"
echo -e "${GREEN}  AnySpark 一键部署${NC}"
echo -e "${GREEN}===========================================${NC}"

# ── 1. 检测 Docker ──
echo ""
echo "[1/5] 检测 Docker..."
if ! command -v docker &>/dev/null; then
    echo -e "${RED}  ✗ Docker 未安装！${NC}"
    echo ""
    echo "  请先安装 Docker："
    echo "    Linux:   curl -fsSL https://get.docker.com | sh"
    echo "    macOS:   https://docs.docker.com/desktop/install/mac-install/"
    echo "    Windows: https://docs.docker.com/desktop/install/windows-install/"
    exit 1
fi
echo -e "${GREEN}  ✓ Docker 已安装${NC}"

# ── 2. 检测 Docker 服务 ──
echo ""
echo "[2/5] 检测 Docker 服务..."
if ! docker info &>/dev/null; then
    echo -e "${RED}  ✗ Docker 服务未运行！${NC}"
    echo ""
    echo "  请启动 Docker："
    echo "    Linux:   sudo systemctl start docker"
    echo "    macOS:   启动 Docker Desktop"
    exit 1
fi
echo -e "${GREEN}  ✓ Docker 服务运行中${NC}"

# ── 3. 配置 .env ──
echo ""
echo "[3/5] 配置环境变量..."
if [ -f .env ]; then
    echo -e "${YELLOW}  ℹ 已存在 .env，跳过配置${NC}"
else
    echo "  首次运行，需要配置："
    echo ""

    read -rp "  请输入 DeepSeek API Key (必填): " apiKey
    if [ -z "$apiKey" ]; then
        echo -e "${RED}  ✗ API Key 不能为空${NC}"
        exit 1
    fi

    read -rp "  Neo4j 密码 (直接回车用默认): " neo4jPass
    neo4jPass="${neo4jPass:-novel_agent_2024!}"

    cat > .env << EOF
DEEPSEEK_API_KEY=$apiKey
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
LLM_MODE=split
NEO4J_PASSWORD=$neo4jPass
SERVER_PORT=8191
EOF
    echo -e "${GREEN}  ✓ .env 已生成${NC}"
fi

# ── 4. 拉取镜像 + 启动 ──
echo ""
echo "[4/5] 拉取镜像并启动..."
mkdir -p data
docker compose pull
docker compose up -d

# ── 5. 等待服务就绪 ──
echo ""
echo "[5/5] 等待服务就绪..."
ready=false
if command -v curl &>/dev/null; then
    for i in $(seq 1 30); do
        if curl -s http://localhost:8190 >/dev/null 2>&1; then
            echo -e "${GREEN}  ✓ 前端已就绪${NC}"
            ready=true
            break
        fi
        echo "  等待中... ($i/30)"
        sleep 3
    done
else
    echo -e "${YELLOW}  ℹ 未检测到 curl，跳过健康检查${NC}"
    echo "  请手动访问 http://localhost:8190 确认服务就绪"
    sleep 10
    ready=true
fi

if [ "$ready" = false ]; then
    echo -e "${YELLOW}  ℹ 服务仍在启动中，请稍后访问${NC}"
    echo "  查看日志：docker compose logs -f"
fi

echo ""
echo -e "${GREEN}===========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}===========================================${NC}"
echo ""
echo "  访问地址：    http://localhost:8190"
echo "  Neo4j 控制台：http://localhost:7474"
echo ""
echo "  常用命令："
echo "    停止：    docker compose down"
echo "    重启：    docker compose restart"
echo "    查看日志：docker compose logs -f"
echo "    更新版本：docker compose pull && docker compose up -d"
echo ""
