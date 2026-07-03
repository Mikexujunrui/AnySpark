#!/usr/bin/env bash
set -euo pipefail

projectDir="$(cd "$(dirname "$0")" && pwd)"
cd "$projectDir"

echo "==========================================="
echo "  AI Novel Writing Agent - Starting..."
echo "==========================================="

# 1. Neo4j
echo "[1/3] Neo4j..."
if ! docker start novel-neo4j >/dev/null 2>&1; then
    echo "  WARN: Neo4j container missing. Run:"
    echo "  docker run -d --name novel-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/novel_agent_2024! neo4j:5-community"
else
    echo "  OK: Neo4j on port 7687"
fi

# 2. Backend
echo "[2/3] Backend (port 8191)..."
# Kill previous backend if running
if [ -f backend.pid ]; then
    kill "$(cat backend.pid)" 2>/dev/null || true
    rm -f backend.pid
fi
python -u src/server.py &
echo $! > backend.pid
sleep 4
echo "  OK"

# 3. Frontend
echo "[3/3] Frontend (port 8190)..."
cd "$projectDir/frontend"
npx vite --port 8190 --host &
FRONTEND_PID=$!
cd "$projectDir"
sleep 4
echo "  OK"

echo ""
echo "==========================================="
echo "  Opening: http://localhost:8190"
echo "==========================================="

# Try to open browser (macOS / Linux)
if command -v open >/dev/null 2>&1; then
    open http://localhost:8190
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open http://localhost:8190
fi

echo ""
echo "  Servers running in background."
echo "  Press Ctrl+C to stop frontend."
echo "==========================================="

# Wait for frontend (keeps script alive)
wait $FRONTEND_PID 2>/dev/null || true
