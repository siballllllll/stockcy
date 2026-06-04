@echo off
chcp 65001 >nul
echo ====================================================
echo        Stockcy Stop
echo ====================================================

echo [*] Step 1: Killing multiprocessing child workers first (reload mode)...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe') -and ($_.CommandLine -like '*multiprocessing.spawn*' -or $_.CommandLine -like '*spawn_main*') } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[OK] killed child PID ' + $_.ProcessId) } catch {} }"

timeout /t 1 /nobreak >nul

echo [*] Step 2: Killing all FastAPI/uvicorn python processes...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe') -and ($_.CommandLine -like '*uvicorn*' -or $_.CommandLine -like '*api.main*' -or $_.CommandLine -like '*run_tunnel*') } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[OK] killed PID ' + $_.ProcessId) } catch {} }"

echo [*] Step 3: Killing process holding port 8000 (last resort)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /f /t /pid %%a >nul 2>&1 && echo [OK] killed port 8000 PID %%a (with tree /T)
)

echo [*] Killing process holding port 3000...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1 && echo [OK] killed port 3000 PID %%a
)

echo [*] Step 4: Killing Cloudflare tunnel (cloudflared + run_cloudflared.py)...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe') -and ($_.CommandLine -like '*run_cloudflared*') } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force; Write-Host ('[OK] killed run_cloudflared PID ' + $_.ProcessId) } catch {} }"
taskkill /f /im cloudflared.exe >nul 2>&1 && echo [OK] killed cloudflared.exe

echo [*] Killing process holding port 3500 (proxy)...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3500 " ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1 && echo [OK] killed port 3500 PID %%a
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
