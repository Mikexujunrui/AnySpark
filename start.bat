@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title AI Novel Writing Agent
cd /d "%~dp0"

echo ===========================================
echo   AI Novel Writing Agent
echo ===========================================
echo.

echo [1/2] Building frontend...
cd /d "%~dp0frontend"
call npx vite build >nul 2>&1
if %errorlevel% neq 0 (
    echo   WARN: Frontend build failed, will use dev mode if available.
) else (
    echo   OK
)
cd /d "%~dp0"

echo [2/2] Starting Backend (port 8191)...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8191"') do taskkill /f /pid %%p >nul 2>&1
start /min "novel-backend" python -u src\server.py
timeout /t 4 /nobreak >nul
echo   OK (minimized)

echo.
echo ===========================================
echo   Opening: http://localhost:8191
echo ===========================================
start http://localhost:8191

echo.
echo   Backend is minimized.
echo   Close this window or press any key to stop.
echo ===========================================
echo.
pause >nul

echo.
echo Stopping servers...
taskkill /f /fi "WINDOWTITLE eq novel-backend" >nul 2>&1
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8191"') do taskkill /f /pid %%p >nul 2>&1
echo Done. Goodbye.
timeout /t 2 /nobreak >nul
