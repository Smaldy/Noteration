@echo off
setlocal enableextensions
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
set "PORT=8000"
set "URL=http://localhost:%PORT%"

rem ============================================================
rem  start.bat - launch Noteration and open it in the browser.
rem  Does NOT rebuild - run build.bat once after code changes.
rem  Shut it down with stop.bat.
rem ============================================================

if not exist "%PY%" (
  echo.
  echo Python virtual environment not found at:
  echo   %PY%
  echo Run build.bat first ^(and create the venv: python -m venv .venv^).
  echo.
  pause
  exit /b 1
)

if not exist "%~dp0dist\index.html" (
  echo.
  echo No built frontend found ^(dist\index.html^).
  echo Run build.bat once before using start.bat.
  echo.
  pause
  exit /b 1
)

rem Already running? Just open the browser instead of starting a second copy.
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo Noteration is already running. Opening %URL% ...
  start "" "%URL%"
  exit /b 0
)

echo Starting the Noteration server on %URL% ...
start "Noteration server" "%PY%" -m uvicorn backend.main:app --port %PORT%

echo Waiting a few seconds for the server to come up...
timeout /t 5 /nobreak >nul
start "" "%URL%"

echo.
echo ============================================
echo   Noteration is running at %URL%
echo   Use stop.bat when you are done.
echo ============================================
exit /b 0
