@echo off
set "SCRIPT_DIR=%~dp0"
set "BAT_FILE=%SCRIPT_DIR%스톡시_원클릭_가동.bat"
set "STARTUP_DIR=%USERPROFILE%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"

if not exist "%BAT_FILE%" (
    echo [ERROR] Cannot find launcher bat file.
    pause
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%STARTUP_DIR%\Stockcy.lnk'); $Shortcut.TargetPath = '%BAT_FILE%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Save()"

echo ===================================================
echo [Stockcy Registered on Startup Successfully]
echo ===================================================
timeout /t 2 >nul
