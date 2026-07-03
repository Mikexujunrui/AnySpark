@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AI Novel Writing Agent
cd /d "%~dp0"

echo ===========================================
echo   AI Novel Writing Agent - Starting...
echo ===========================================

:: 1. Neo4j
echo [1/3] Neo4j...
docker start novel-neo4j >nul 2>&1
if %errorlevel% neq 0 (
    echo   WARN: Neo4j container missing. Run:
    echo   docker run -d --name novel-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/novel_agent_2024! neo4j:5.26-community
) else (
    echo   OK: Neo4j on port 7687
)

:: 2. Backend
echo [2/3] Backend (port 8191)...
:: Stop previous backend by PID file (avoid killing all python)
if exist backend.pid (
    set /p OLD_PID=<backend.pid
    taskkill /f /pid !OLD_PID! >nul 2>&1
    del backend.pid >nul 2>&1
)
start /min "novel-backend" python -u src\server.py
:: Save PID for next restart
timeout /t 1 /nobreak >nul
for /f "tokens=2" %%i in ('tasklist /fi "windowtitle eq novel-backend*" /fo list ^| findstr "PID:"') do echo %%i>backend.pid
timeout /t 4 /nobreak >nul
echo   OK

:: 3. Frontend
echo [3/3] Frontend (port 8190)...
start /min "novel-frontend" cmd /c "cd /d %~dp0frontend && npx vite --port 8190 --host"
timeout /t 5 /nobreak >nul
echo   OK

echo.
echo ===========================================
echo   Opening: http://localhost:8190
echo ===========================================
start http://localhost:8190

echo.
echo   Servers running in background.
echo   Close this window, servers keep running.
echo   Double-click start.bat to restart.
echo ===========================================
pause
