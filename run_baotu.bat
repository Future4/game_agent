@echo off
setlocal
cd /d "%~dp0"

rem ---- 1) 需要管理员权限：游戏通常以管理员运行，非管理员进程的点击会被系统拦截 ----
net session >nul 2>&1
if errorlevel 1 (
    echo [INFO] Requesting administrator privileges...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

rem ---- 2) 选择合适的解释器（不要用 WindowsApps 里的 python 商店占位程序）----
set "PYEXE=py"
where py >nul 2>&1
if errorlevel 1 set "PYEXE=D:\Anaconda3\python.exe"

echo [INFO] Python: %PYEXE%
%PYEXE% -V
echo [INFO] Run: mainMaa.py baotu
echo.
%PYEXE% mainMaa.py baotu
echo.
echo [INFO] Finished. Press any key to close.
pause >nul
