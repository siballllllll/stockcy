@echo off
set "ROOT_DIR=%~dp0"
set "FRONT_DIR=%~dp0frontend"

start "Stockcy_Backend" cmd /k "title 스톡시 백엔드 (8000) && cd /d "%ROOT_DIR%" && .\venv\Scripts\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"
start "Stockcy_Frontend" cmd /k "title 스톡시 프론트엔드 (3000) && cd /d "%FRONT_DIR%" && call npm run dev"
