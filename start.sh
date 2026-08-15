#!/bin/bash
# ============================================================
# AnySpark v4 — Linux / macOS 一键启动
#   Windows 用 start.bat；本脚本覆盖 macOS + Linux（源码运行）
#   依赖：uv + Node.js 20+（首次安装会自动执行）
# ============================================================
set -e
cd "$(dirname "$0")"

echo
echo "  ============================================"
echo "    AnySpark v4  创作台启动中..."
echo "  ============================================"
echo

# ---- 0. 释放残留端口（上次未正常关闭时用）----
echo "  [0/5] 清理残留进程..."
for port in 8000 5173; do
  if command -v lsof >/dev/null 2>&1; then
    pid=$(lsof -ti tcp:$port 2>/dev/null || true)
    if [ -n "$pid" ]; then
      echo "       端口 $port 被 PID $pid 占用，已清理"
      kill $pid 2>/dev/null || true
    fi
  fi
done

# ---- 1. 检查 .env（缺则复制模板）----
if [ ! -f ".env" ]; then
  echo "  [1/5] 未找到 .env，已从模板生成——请填入 DEEPSEEK_API_KEY 后重跑"
  cp .env.example .env
  exit 1
fi

# ---- 2. 后端环境（首次才安装）----
echo "  [2/5] 检查 Python 环境..."
if [ ! -d ".venv" ]; then
  echo "       首次安装 Python 依赖（需要联网 + 已装 uv）..."
  command -v uv >/dev/null 2>&1 || { echo "  [错误] 未找到 uv，请先安装: https://docs.astral.sh/uv/"; exit 1; }
  uv sync
else
  echo "       环境已就绪"
fi

# ---- 3. 前端依赖（首次才安装）----
echo "  [3/5] 检查前端依赖..."
if [ ! -d "frontend/node_modules" ]; then
  echo "       首次安装前端依赖（需要网络）..."
  (cd frontend && npm ci)
fi
echo "       前端依赖就绪"

# ---- 4. 启动后端 ----
echo "  [4/5] 启动后端 127.0.0.1:8000 ..."
echo "        日志文件: data/logs/anyspark.log"
mkdir -p data/logs
uv run anyspark-server --port 8000 >> data/logs/anyspark.log 2>&1 &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT

# 等后端就绪（最多 30s）
echo "        等待后端就绪..."
for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "        后端已就绪 ✓"
    break
  fi
  [ "$i" = "30" ] && echo "  [警告] 后端 30s 未就绪，请查 data/logs/anyspark.log"
  sleep 1
done

# ---- 5. 启动前端 + 打开浏览器 ----
echo "  [5/5] 启动前端 http://127.0.0.1:5173 ..."
(cd frontend && npm run dev) &
FRONTEND_PID=$!
trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true' EXIT

sleep 3
if command -v open >/dev/null 2>&1; then
  open http://127.0.0.1:5173 2>/dev/null || true   # macOS
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open http://127.0.0.1:5173 2>/dev/null || true  # Linux
fi

echo
echo "  创作台已启动：http://127.0.0.1:5173"
echo "  退出：Ctrl+C（同时停止后端与前端）"
echo

wait
