@echo off
chcp 65001 >nul
echo ====================================================
echo        Stockcy Stop
echo ====================================================

echo [*] Stopping FastAPI (uvicorn)...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*uvicorn*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue; Write-Host ('[OK] PID ' + $_.ProcessId) }"

echo [*] Stopping Node.js...
taskkill /f /im node.exe >nul 2>&1

taskkill /f /fi "WINDOWTITLE eq Stockcy Backend (8000)" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Stockcy Frontend (3000)" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Stockcy Proxy (3500)" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Stockcy Mobile Tunnel" >nul 2>&1

echo [DONE] All Stockcy servers stopped.
timeout /t 2 >nul
