@echo off
rem ============================================
rem  AnySpark v4 - Windows 一键启动（双击即用）
rem  后端直接用 .venv 里的程序，不依赖 PATH 的 uv
rem  编码：UTF-8 无 BOM + CRLF（匹配系统代码页 65001）
rem ============================================
setlocal
cd /d "%~dp0"

echo.
echo  ============================================
echo    AnySpark v4  创作台启动中...
echo  ============================================
echo.

rem ---- 0. 释放残留端口（上次未正常关闭时必用）----
echo  [0/4] 清理残留进程...
call :freeport 8000
call :freeport 5173
echo.

rem ---- 1. 检查 .env（缺则复制模板）----
if not exist ".env" (
    echo  [提示] 未找到 .env 配置文件
    echo  请复制 .env.example 为 .env 并填入 DeepSeek API Key
    copy ".env.example" ".env" >nul
    echo  已自动生成 .env 模板，请手动填入真实 key 后重新运行
    echo.
)

rem ---- 2. 后端环境（首次才安装）----
echo  [1/4] 检查 Python 环境...
if not exist ".venv" (
    echo       首次安装 Python 依赖（需要联网 + 已装 uv）...
    echo       若提示 uv 不存在，请先安装 uv: https://docs.astral.sh/uv/
    uv sync
    if errorlevel 1 (
        echo.
        echo  [错误] 依赖安装失败，请确认已安装 uv 且网络通畅
        pause
        exit /b 1
    )
) else (
    echo       环境已就绪
)
echo.

rem ---- 3. 前端依赖（首次才安装）----
echo  [2/4] 检查前端依赖...
if not exist "frontend\node_modules" (
    echo       首次安装前端依赖（需要网络）...
    pushd frontend
    call npm ci
    popd
)
echo       前端依赖就绪
echo.

rem ---- 4. 启动后端（.venv 里的程序）----
echo  [3/4] 启动后端 127.0.0.1:8000 ...
echo        日志文件: data\logs\anyspark.log

echo        日志文件: data\logsnyspark.log
if exist ".venv\Scripts\anyspark-server.exe" (
    start "AnySpark-Backend" cmd /k "cd /d %~dp0 && .venv\Scripts\anyspark-server.exe --port 8000"
) else (
    echo  [错误] 未找到 .venv\Scripts\anyspark-server.exe，请删除 .venv 后重新运行
    pause
    exit /b 1
)

rem ---- 5. 启动前端 ----
echo  [4/4] 启动前端 localhost:5173 ...
pushd "%~dp0frontend"
start "AnySpark-Frontend" cmd /k "npm run dev"
popd

echo.
echo  正在等待两个服务启动，稍后会自动打开浏览器...
"%SystemRoot%\System32\timeout.exe" /t 10 /nobreak >nul

rem ---- 6. 打开浏览器 ----
start "" "http://localhost:5173"

echo.
echo  创作台已启动
echo  若浏览器未自动打开，请手动访问:
echo    http://localhost:5173
echo.
echo  退出时请关闭所有黑色窗口
echo.
pause
exit /b 0

rem ============================================
rem  辅助：按端口号杀掉占用进程
rem  用法: call :freeport 8000
rem ============================================
:freeport
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%1 " ^| findstr "LISTENING"') do (
    echo      端口 %1 被 PID %%p 占用，已自动清理
    taskkill /F /PID %%p >nul 2>&1
)
goto :eof
