#!/usr/bin/env bash
# AnySpark v4 — 一键开发启动（后端 + 前端）
# 用法：bash scripts/dev.sh
set -e
cd "$(dirname "$0")/.."

echo "== 启动后端 (127.0.0.1:8000) =="
uv run anyspark-server --port 8000 &
BACKEND_PID=$!

echo "== 启动前端 (localhost:5173) =="
cd frontend
npm run dev &
FRONTEND_PID=$!

trap 'echo "停止中…"; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null' EXIT INT TERM
wait
