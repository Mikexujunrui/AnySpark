@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AI Novel Writing Agent
cd /d "%~dp0"

echo ===========================================
echo   AI Novel Writing Agent - Starting...
echo ===========================================

echo [1/3] Neo4j...
docker start novel-neo4j >nul 2>&1
if %errorlevel% neq 0 (
    echo   WARN: Neo4j container missing
) else (
    echo   OK: Neo4j on port 7687
)

echo [2/3] Backend (port 8191)...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8191"') do taskkill /f /pid %%p >nul 2>&1
start "novel-backend" python -u src\server.py
timeout /t 3 /nobreak >nul
echo   OK

echo [3/3] Frontend (port 8190)...
start "novel-frontend" cmd /c "cd /d %~dp0frontend && npx vite --port 8190 --host"
timeout /t 4 /nobreak >nul
echo   OK

echo.
echo ===========================================
echo   Opening: http://localhost:8190
echo ===========================================
start http://localhost:8190

echo.
echo   Backend window stays open on crash.
echo   Close this window to quit.
echo ===========================================
pause