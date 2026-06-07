@echo off
setlocal enableextensions
rem Re-assert core Windows dirs on PATH; some installs drop System32, which
rem breaks the built-in timeout used below. %SystemRoot% is always set.
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%SystemRoot%\System32\WindowsPowerShell\v1.0;%PATH%"
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

echo [1/3] Building the frontend ^(this takes ~2-3 minutes - it is NOT frozen,
echo       the plotly bundle is large; wait for the file list to print^)...
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
rem /d sets the working dir; cmd /k keeps the window open so uvicorn errors stay
rem readable. Quote only the exe path inside the cmd /k string.
start "Noteration server" /d "%ROOT%" cmd /k ""%PY%" -m uvicorn backend.main:app --port 8000"

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
