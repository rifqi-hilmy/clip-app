@echo off
REM Starts backend (FastAPI :8000) and frontend (Vite :5173) in separate windows.
set ROOT=%~dp0

if not exist "%ROOT%tools\ffmpeg\bin\ffmpeg.exe" (
  echo [setup] FFmpeg not found, downloading portable build...
  powershell -ExecutionPolicy Bypass -File "%ROOT%scripts\setup_tools.ps1"
)

if not exist "%ROOT%backend\.venv\Scripts\python.exe" (
  echo [setup] Creating Python venv...
  python -m venv "%ROOT%backend\.venv"
  "%ROOT%backend\.venv\Scripts\python.exe" -m pip install -r "%ROOT%backend\requirements.txt"
)

if not exist "%ROOT%frontend\node_modules" (
  echo [setup] Installing frontend deps...
  pushd "%ROOT%frontend" && call npm install && popd
)

start "clip-backend" cmd /k "cd /d %ROOT%backend && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"
start "clip-frontend" cmd /k "cd /d %ROOT%frontend && npm run dev"

timeout /t 4 >nul
start http://localhost:5173
