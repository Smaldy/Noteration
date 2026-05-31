@echo off
setlocal enableextensions
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"

rem ============================================================
rem  build.bat - rebuild the frontend bundle and apply database
rem  migrations. Run this only when the code or schema changed;
rem  for day-to-day use just run start.bat.
rem ============================================================

if not exist "%PY%" (
  echo.
  echo Python virtual environment not found at:
  echo   %PY%
  echo Create it first from this folder:  python -m venv .venv
  echo.
  pause
  exit /b 1
)

echo ============================================
echo   Noteration - build ^& prepare
echo ============================================
echo.

echo [1/2] Building the frontend ^(takes ~20s^)...
call npm run build
if errorlevel 1 (
  echo.
  echo Frontend build failed. See the messages above.
  pause
  exit /b 1
)

echo.
echo [2/2] Applying database migrations...
pushd "%~dp0backend"
"%PY%" -m alembic upgrade head
if errorlevel 1 (
  popd
  echo.
  echo Database migration failed. See the messages above.
  pause
  exit /b 1
)
popd

echo.
echo ============================================
echo   Build complete. Run start.bat to launch.
echo ============================================
echo.
pause
