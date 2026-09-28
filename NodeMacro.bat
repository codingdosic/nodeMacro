@echo off
setlocal
cd /d "%~dp0"

python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=1)" >nul 2>&1
if errorlevel 1 (
    start "NodeMacro Server" /min python backend\main.py
    for /l %%i in (1,1,20) do (
        python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=1)" >nul 2>&1 && goto ready
        timeout /t 1 /nobreak >nul
    )
    echo NodeMacro server failed to start.
    exit /b 1
)

:ready
if /i not "%~1"=="--no-browser" start "" http://127.0.0.1:8000
