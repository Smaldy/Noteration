@echo off
setlocal enableextensions
set "PORT=8000"

rem ============================================================
rem  stop.bat - shut down the running Noteration server: kill
rem  whatever listens on the port, then close its console window.
rem ============================================================

set "FOUND="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
  set "FOUND=1"
  echo Stopping Noteration ^(PID %%a^)...
  taskkill /F /PID %%a >nul 2>&1
)

rem Close the leftover "Noteration server" console window, if it is still open.
taskkill /F /T /FI "WINDOWTITLE eq Noteration server*" >nul 2>&1

if not defined FOUND (
  echo Noteration does not appear to be running on port %PORT%.
) else (
  echo Noteration stopped.
)
echo.
pause
