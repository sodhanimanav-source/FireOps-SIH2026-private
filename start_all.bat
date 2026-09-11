@echo off
title FireOps System Launcher
echo ========================================================
echo        Starting FireOps Command System (v3.0)
echo ========================================================

set "PATH=C:\Users\nikhi\anaconda3;C:\Users\nikhi\anaconda3\Scripts;C:\Program Files\nodejs;%PATH%"

echo.
echo [1/2] Launching Backend Server on port 8000...
start "FireOps Backend (Uvicorn)" cmd /k "cd /d "%~dp0backend_files" && python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

timeout /t 3 /nobreak >nul

echo.
echo [2/2] Launching Frontend Dashboard on port 5173...
start "FireOps Frontend (Vite)" cmd /k "cd /d "%~dp0Frontend" && npm run dev"

echo.
echo ========================================================
echo  Both services launched!
echo  Frontend: http://localhost:5173
echo  Backend:  http://127.0.0.1:8000
echo ========================================================
echo.
pause
