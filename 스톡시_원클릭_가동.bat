@echo off
title Stockcy Launcher
chcp 65001 >nul
set "ROOT=%~dp0"
cd /d "%ROOT%"

echo ====================================================
echo        Stockcy Startup
echo ====================================================

if not exist "%ROOT%venv\Scripts\python.exe" (
    echo [ERROR] venv not found.
    pause
    exit /b 1
)

netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [SKIP] Port 8000 already in use.
) else (
    echo [+] Starting FastAPI backend on port 8000...
    start "Stockcy_Backend" cmd /k %ROOT%_start_backend.bat
)

netstat -ano | findstr ":3000 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [SKIP] Port 3000 already in use.
) else (
    echo [+] Starting Next.js frontend on port 3000...
    start "Stockcy_Frontend" cmd /k %ROOT%_start_frontend.bat
)

if exist "%ROOT%scratch\dev_proxy.js" (
    netstat -ano | findstr ":3500 " | findstr "LISTENING" >nul 2>&1
    if errorlevel 1 (
        echo [+] Starting proxy on port 3500...
        start "Stockcy_Proxy" cmd /k "title Stockcy Proxy (3500) && cd /d %ROOT% && node scratch\dev_proxy.js"
    ) else (
        echo [SKIP] Port 3500 already in use.
    )
)

if exist "%ROOT%scratch\run_tunnel.py" (
    echo [+] Starting ngrok tunnel...
    start "Stockcy_Tunnel" cmd /k "title Stockcy Mobile Tunnel && cd /d %ROOT% && .\venv\Scripts\python.exe scratch\run_tunnel.py"
)

echo.
echo [DONE] All services launched.
echo [INFO] Backend:  http://localhost:8000
echo [INFO] Frontend: http://localhost:3000
timeout /t 3 >nul
