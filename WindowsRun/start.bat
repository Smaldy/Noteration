@echo off
setlocal enableextensions enabledelayedexpansion
rem This script lives in WindowsRun\, so the project root is one level up.
cd /d "%~dp0.."
set "ROOT=%CD%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
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

if not exist "%ROOT%\dist\index.html" (
  echo.
  echo No built frontend found ^(dist\index.html^).
  echo Run build.bat once before using start.bat.
  echo.
  pause
  exit /b 1
)

rem Already serving? Just open the browser instead of starting a second copy.
set "RUNNING="
for /f %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do set "RUNNING=1"
if defined RUNNING (
  echo Noteration already appears to be running. Opening %URL% ...
  start "" "%URL%"
  exit /b 0
)

echo Starting the Noteration server in a new window...
rem cmd /k keeps the window open if uvicorn errors, so you can read the message.
start "Noteration server" cmd /k "cd /d "%ROOT%" ^&^& "%PY%" -m uvicorn backend.main:app --port %PORT%"

echo Waiting for the server to be ready ^(up to 30s on a cold start^)...
set /a tries=0
:waitloop
timeout /t 1 /nobreak >nul
set "READY="
for /f %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do set "READY=1"
if defined READY goto ready
set /a tries+=1
if !tries! geq 30 goto failed
goto waitloop

:ready
start "" "%URL%"
echo.
echo ============================================
echo   Noteration is running at %URL%
echo   Keep the "Noteration server" window open.
echo   Use stop.bat when you are done.
echo ============================================
exit /b 0

:failed
echo.
echo The server did not become ready within 30 seconds.
echo Look at the "Noteration server" window for an error message.
echo If you have not built the app yet, close it and run build.bat first.
echo.
pause
exit /b 1
