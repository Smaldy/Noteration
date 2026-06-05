#!/usr/bin/env bash
# ============================================================
#  build.command - rebuild the frontend bundle and apply database
#  migrations. Run this only when the code or schema changed;
#  for day-to-day use just run start.command.
#  (Double-clickable in Finder. macOS equivalent of build.bat.)
# ============================================================
set -uo pipefail

# This script lives in MacRun/, so the project root is one level up.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
cd "$ROOT"

pause() { echo; read -n 1 -s -r -p "Press any key to close..."; echo; }

if [ ! -x "$PY" ]; then
  echo
  echo "Python virtual environment not found at:"
  echo "  $PY"
  echo "Create it first from the project root:  python3 -m venv .venv"
  pause
  exit 1
fi

echo "============================================"
echo "  Noteration - build & prepare"
echo "============================================"
echo

echo "[1/2] Building the frontend (takes ~20s)..."
if ! npm run build; then
  echo
  echo "Frontend build failed. See the messages above."
  pause
  exit 1
fi

echo
echo "[2/2] Applying database migrations..."
if ! ( cd "$ROOT/backend" && "$PY" -m alembic upgrade head ); then
  echo
  echo "Database migration failed. See the messages above."
  pause
  exit 1
fi

echo
echo "============================================"
echo "  Build complete. Run start.command to launch."
echo "============================================"
pause
