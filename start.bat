@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AI Novel Writing Agent
cd /d "%~dp0"

echo ===========================================
echo   AI Novel Writing Agent
echo ===========================================
echo.

echo [1/3] Neo4j...
docker start novel-neo4j >nul 2>&1
if %errorlevel% neq 0 (
    echo   Creating Neo4j container...
    docker run -d --name novel-neo4j ^
        -p 7474:7474 -p 7687:7687 ^
        -e NEO4J_AUTH=neo4j/novel_agent_2024! ^
        -e NEO4J_PLUGINS="[]" ^
        neo4j:5.26-community >nul 2>&1
    if %errorlevel% neq 0 (
        echo   ERROR: Failed to create Neo4j container. Is Docker running?
        echo   知识库功能将不可用。请安装 Docker Desktop 后重试。
    ) else (
        echo   OK: Neo4j created and started on port 7687
        echo   (首次启动需等待约30秒初始化)
        timeout /t 30 /nobreak >nul
    )
) else (
    echo   OK: Neo4j on port 7687
)

echo [2/3] Backend (port 8191)...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8191"') do taskkill /f /pid %%p >nul 2>&1
start /min "novel-backend" python -u src\server.py
timeout /t 3 /nobreak >nul
echo   OK (minimized)

echo [3/3] Frontend (port 8190)...
start /min "novel-frontend" cmd /c "cd /d %~dp0frontend && npx vite --port 8190 --host"
timeout /t 4 /nobreak >nul
echo   OK (minimized)

echo.
echo ===========================================
echo   Opening: http://localhost:8190
echo ===========================================
start http://localhost:8190

echo.
echo   Backend ^& Frontend are minimized to taskbar.
echo   Close this window or press any key to stop.
echo ===========================================
echo.
pause >nul

echo.
echo Stopping servers...
taskkill /f /fi "WINDOWTITLE eq novel-backend" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq novel-frontend" >nul 2>&1
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8191"') do taskkill /f /pid %%p >nul 2>&1
echo Done. Goodbye.
timeout /t 2 /nobreak >nul@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AI Novel Writing Agent
cd /d "%~dp0"

echo ===========================================
echo   AI Novel Writing Agent
echo ===========================================
echo.

echo [1/4] Neo4j...
docker start novel-neo4j >nul 2>&1
if %errorlevel% neq 0 (
    echo   WARN: Neo4j container missing
) else (
    echo   OK: Neo4j on port 7687
)

echo [2/4] Backend (port 8191)...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8191"') do taskkill /f /pid %%p >nul 2>&1
start /min "novel-backend" python -u src\server.py
timeout /t 3 /nobreak >nul
echo   OK (minimized)

echo [3/4] Frontend (port 8190)...
start /min "novel-frontend" cmd /c "cd /d %~dp0frontend && npx vite --port 8190 --host"
timeout /t 4 /nobreak >nul
echo   OK (minimized)

echo.
echo ===========================================
echo   Opening: http://localhost:8190
echo ===========================================
start http://localhost:8190

echo.
echo   Backend ^& Frontend are minimized to taskbar.
echo   Close this window or press any key to stop.
echo ===========================================
echo.
pause >nul

echo.
echo Stopping servers...
taskkill /f /fi "WINDOWTITLE eq novel-backend" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq novel-frontend" >nul 2>&1
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8191"') do taskkill /f /pid %%p >nul 2>&1
echo Done. Goodbye.
timeout /t 2 /nobreak >nul
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