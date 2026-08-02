@echo off
rem ============================================
rem  AnySpark v4 - Windows 一键启动
rem  双击本文件即可：起后端 + 起前端 + 开浏览器
rem ============================================
cd /d "%~dp0"

echo.
echo  ============================================
echo    AnySpark v4  创作台启动中...
echo  ============================================
echo.

rem ---- 1. 检查 .env（真实模型 key）----
if not exist ".env" (
    echo  [警告] 未找到 .env 配置文件
    echo  请复制 .env.example 为 .env 并填入 DeepSeek API Key
    copy ".env.example" ".env" >nul
    echo  已自动创建 .env 模板，请用记事本填入真实 key 后重新启动
    echo.
)

rem ---- 2. 安装 Python 依赖（首次才安装）----
echo  [1/4] 检查 Python 依赖...
if not exist ".venv" (
    echo        首次安装 Python 依赖，可能需要几分钟（需联网）...
    uv sync
    if errorlevel 1 (
        echo.
        echo  [错误] uv sync 失败。可能原因：
        echo    1. 未安装 uv ^(https://docs.astral.sh/uv/^)
        echo    2. 网络不通 / 首次下载超时
        echo  修复后重新双击本文件即可。
        pause
        exit /b 1
    )
) else (
    echo        依赖已就绪（跳过安装）
)
echo.

rem ---- 3. 安装前端依赖（首次）----
echo  [2/4] 检查前端依赖...
if not exist "frontend\node_modules" (
    echo        首次安装前端依赖，可能需要几分钟...
    pushd frontend
    call npm ci
    popd
)
echo        前端依赖就绪
echo.

rem ---- 4. 启动后端 ----
echo  [3/4] 启动后端 127.0.0.1:8000 ...
pushd "%~dp0"

start "AnySpark-Backend" cmd /k "uv run anyspark-server --port 8000"

popd

rem ---- 5. 启动前端 ----
echo  [4/4] 启动前端 localhost:5173 ...
pushd "%~dp0frontend"

start "AnySpark-Frontend" cmd /k "npm run dev"

popd

echo.
echo  正在等待服务就绪，稍后自动打开浏览器...
echo  （两个黑色窗口请勿关闭，关闭即退出 AnySpark）
"%SystemRoot%\System32\timeout.exe" /t 10 /nobreak >nul

rem ---- 6. 打开浏览器 ----
start "" "http://localhost:5173"

echo.
echo  创作台已启动！
echo  浏览器若未自动打开，请手动访问：
echo    http://localhost:5173
echo.
echo  退出方法：关闭两个命令行窗口
echo.
pause
