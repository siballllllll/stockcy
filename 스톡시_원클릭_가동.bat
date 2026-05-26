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
    wscript.exe "%ROOT%_run_hidden.vbs" "cmd.exe /c cd /d ""%ROOT%"" && .\venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"
)

netstat -ano | findstr ":3000 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [SKIP] Port 3000 already in use.
) else (
    echo [+] Starting Next.js frontend on port 3000...
    wscript.exe "%ROOT%_run_hidden.vbs" "cmd.exe /c set PATH=%%PATH%%;C:\Program Files\nodejs\ && cd /d ""%ROOT%frontend"" && call npm run dev"
)

if exist "%ROOT%scratch\dev_proxy.js" (
    netstat -ano | findstr ":3500 " | findstr "LISTENING" >nul 2>&1
    if errorlevel 1 (
        echo [+] Starting proxy on port 3500...
        wscript.exe "%ROOT%_run_hidden.vbs" "cmd.exe /c set PATH=%%PATH%%;C:\Program Files\nodejs\ && cd /d ""%ROOT%"" && node scratch\dev_proxy.js"
    ) else (
        echo [SKIP] Port 3500 already in use.
    )
)

if exist "%ROOT%scratch\run_tunnel.py" (
    echo [+] Starting ngrok tunnel...
    wscript.exe "%ROOT%_run_hidden.vbs" "cmd.exe /c cd /d ""%ROOT%"" && .\venv\Scripts\python.exe scratch\run_tunnel.py"
)

echo.
echo [DONE] All services launched in background.
echo [INFO] Backend:  http://localhost:8000
echo [INFO] Frontend: http://localhost:3000
timeout /t 3 >nul
