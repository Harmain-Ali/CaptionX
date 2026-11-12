@echo off
REM One command to set up and run everything on Windows: double-click run.bat
cd /d "%~dp0"

where python >nul 2>nul || (echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1)
where node   >nul 2>nul || (echo Node.js 18+ is required: https://nodejs.org & pause & exit /b 1)
where pnpm   >nul 2>nul || (echo pnpm is required. Run:  npm install -g pnpm & pause & exit /b 1)
where ffmpeg >nul 2>nul || echo WARNING: ffmpeg not found. Install it with:  winget install Gyan.FFmpeg   (then reopen this window)

echo === Backend setup ===
cd backend
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
pip install -q -r requirements.txt
cd ..

echo === Frontend setup ===
cd frontend
call pnpm install
cd ..

echo === Starting ===
start "Captions backend" cmd /k "cd /d %~dp0backend && call .venv\Scripts\activate.bat && python run.py"
start "Captions frontend" cmd /k "cd /d %~dp0frontend && pnpm dev --host 127.0.0.1"
timeout /t 4 >nul
start http://localhost:5173
