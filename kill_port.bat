@echo off
rem ============================================
rem  按端口清理占用进程（防止残留进程导致启动失败）
rem  用法: kill_port.bat 8000  或  kill_port.bat 5173
rem  编码：UTF-8 无 BOM + CRLF（匹配系统代码页 65001）
rem ============================================
setlocal
set "PORT=%~1"
if "%PORT%"=="" (
    echo 用法: kill_port.bat ^<端口号^>
    echo 例:   kill_port.bat 8000
    pause
    exit /b 1
)

echo 正在查找端口 %PORT% 的占用进程...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo  找到 PID %%p 占用端口 %PORT%，正在结束...
    taskkill /F /PID %%p >nul 2>&1
)
echo 完成
