@echo off
setlocal enableextensions
rem This script lives in WindowsRun\, so the project root is one level up.
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"

rem ============================================================
rem  Noteration.bat - one-click build + run. Builds the frontend,
rem  applies migrations, then starts the server and opens the app.
rem ============================================================

if not exist "%PY%" (
  echo.
  echo Python virtual environment not found at:
  echo   %PY%
  echo Create it first from the project root:  python -m venv .venv
  echo.
  pause
  exit /b 1
)

echo ============================================
echo   Noteration - building and starting
echo ============================================
echo.

echo [1/3] Building the frontend ^(takes ~20s the first time^)...
call npm run build
if errorlevel 1 (
  echo.
  echo Frontend build failed. See the messages above.
  pause
  exit /b 1
)

echo.
echo [2/3] Applying database migrations...
pushd "%ROOT%\backend"
"%PY%" -m alembic upgrade head
popd

echo.
echo [3/3] Starting the server in a new window...
start "Noteration server" "%PY%" -m uvicorn backend.main:app --port 8000

echo Waiting a few seconds for the server to come up...
timeout /t 6 /nobreak >nul
start "" "http://localhost:8000"

echo.
echo ============================================
echo   Noteration is running at http://localhost:8000
echo   A separate "Noteration server" window opened.
echo   Close that window to stop the app.
echo ============================================
echo.
pause
