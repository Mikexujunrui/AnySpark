@echo off
rem ============================================
rem  按端口安全清理进程（不会误杀其它程序）
rem  用法: kill_port.bat 8000   或   kill_port.bat 5173
rem ============================================
set "PORT=%~1"
if "%PORT%"=="" (
    echo 用法: kill_port.bat ^<端口号^>
    echo 例: kill_port.bat 8000
    pause
    exit /b 1
)

echo 正在查找端口 %PORT% 的占用进程...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo  找到 PID %%p 占用端口 %PORT%，正在结束...
    taskkill /F /PID %%p
)
echo 完成。
