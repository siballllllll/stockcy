@echo off
chcp 65001 >nul
echo ====================================================
echo        Stockcy Stop
echo ====================================================

echo [*] Killing all FastAPI/uvicorn python processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe') -and ($_.CommandLine -like '*uvicorn*' -or $_.CommandLine -like '*api.main*' -or $_.CommandLine -like '*run_tunnel*') } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[OK] killed PID ' + $_.ProcessId) } catch {} }"

echo [*] Killing process holding port 8000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1 && echo [OK] killed port 8000 PID %%a
)

echo [*] Killing process holding port 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1 && echo [OK] killed port 3000 PID %%a
)

echo [*] Stopping Node.js...
taskkill /f /im node.exe >nul 2>&1

taskkill /f /fi "WINDOWTITLE eq Stockcy Backend (8000)" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Stockcy Frontend (3000)" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Stockcy Proxy (3500)" >nul 2>&1
taskkill /f /fi "WINDOWTITLE eq Stockcy Mobile Tunnel" >nul 2>&1

echo.
echo [DONE] All Stockcy servers stopped.
timeout /t 2 >nul
