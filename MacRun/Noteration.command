#!/usr/bin/env bash
# ============================================================
#  Noteration.command - one-click build + run. Builds the frontend,
#  applies migrations, then starts the server and opens the app.
#  (Double-clickable in Finder. macOS equivalent of Noteration.bat.)
# ============================================================
set -uo pipefail

# This script lives in MacRun/, so the project root is one level up.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
PORT=8000
URL="http://localhost:$PORT"
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
echo "  Noteration - building and starting"
echo "============================================"
echo

echo "[1/3] Building the frontend (takes ~20s the first time)..."
if ! npm run build; then
  echo
  echo "Frontend build failed. See the messages above."
  pause
  exit 1
fi

echo
echo "[2/3] Applying database migrations..."
( cd "$ROOT/backend" && "$PY" -m alembic upgrade head )

echo
echo "[3/3] Starting the server in a new Terminal window..."
osascript >/dev/null 2>&1 <<EOF
tell application "Terminal"
  activate
  do script "cd '$ROOT' && '$PY' -m uvicorn backend.main:app --port $PORT"
end tell
EOF

echo "Waiting a few seconds for the server to come up..."
sleep 6
open "$URL"

echo
echo "============================================"
echo "  Noteration is running at $URL"
echo "  A separate \"Noteration server\" Terminal window opened."
echo "  Close that window (or run stop.command) to stop the app."
echo "============================================"
pause
