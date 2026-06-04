@echo off
set "SCRIPT_DIR=%~dp0"
set "VBS_FILE=%SCRIPT_DIR%stockcy_silent_run.vbs"
set "STARTUP_DIR=%USERPROFILE%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup"

if not exist "%VBS_FILE%" (
    echo [ERROR] Cannot find launcher vbs file.
    pause
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%STARTUP_DIR%\Stockcy.lnk'); $Shortcut.TargetPath = '%VBS_FILE%'; $Shortcut.WorkingDirectory = '%SCRIPT_DIR%'; $Shortcut.Save()"

echo ===================================================
echo [Stockcy Registered on Startup Successfully]
echo ===================================================
timeout /t 2 >nul
