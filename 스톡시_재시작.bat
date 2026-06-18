@echo off
chcp 65001 >nul
title Stockcy Restart
echo ====================================================
echo        Stockcy Restart  (Stop -^> Wait -^> Start)
echo ====================================================
echo  * One click: stops everything, then relaunches.
echo  * Reduces the 502 gap (no manual delay between two scripts).
echo ----------------------------------------------------

echo.
echo [STOP 1/4] Killing reload child workers...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe') -and ($_.CommandLine -like '*multiprocessing.spawn*' -or $_.CommandLine -like '*spawn_main*') } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('[OK] child ' + $_.ProcessId) } catch {} }"
timeout /t 1 /nobreak >nul

echo [STOP 2/4] Killing uvicorn / api.main ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe') -and ($_.CommandLine -like '*uvicorn*' -or $_.CommandLine -like '*api.main*' -or $_.CommandLine -like '*run_tunnel*') } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('[OK] ' + $_.ProcessId) } catch {} }"

echo [STOP 3/4] Freeing ports 8000 / 3000 / 3500 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do taskkill /f /t /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":3500 " ^| findstr "LISTENING"') do taskkill /f /pid %%a >nul 2>&1

echo [STOP 4/4] Killing cloudflared / node ...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'python.exe') -and ($_.CommandLine -like '*run_cloudflared*') } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }"
taskkill /f /im cloudflared.exe >nul 2>&1
taskkill /f /im node.exe >nul 2>&1

echo.
echo [WAIT] Letting ports settle (4s)...
timeout /t 4 /nobreak >nul

echo.
echo [START] Launching servers via stockcy_silent_run.vbs ...
wscript "%~dp0stockcy_silent_run.vbs"

echo.
echo [DONE] Restarted. Open stockcy.trade in ~20-30 seconds.
echo        (If 502 appears, just wait a bit and refresh.)
timeout /t 3 >nul
