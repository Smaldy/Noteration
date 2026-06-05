#!/usr/bin/env bash
# ============================================================
#  start.command - launch Noteration and open it in the browser.
#  Does NOT rebuild - run build.command once after code changes.
#  Shut it down with stop.command.
#  (Double-clickable in Finder. macOS equivalent of start.bat.)
# ============================================================
set -uo pipefail

# This script lives in MacRun/, so the project root is one level up.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/.venv/bin/python"
PORT=8000
URL="http://localhost:$PORT"
cd "$ROOT"

pause() { echo; read -n 1 -s -r -p "Press any key to close..."; echo; }

port_in_use() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; }

if [ ! -x "$PY" ]; then
  echo
  echo "Python virtual environment not found at:"
  echo "  $PY"
  echo "Run build.command first (and create the venv: python3 -m venv .venv)."
  pause
  exit 1
fi

if [ ! -f "$ROOT/dist/index.html" ]; then
  echo
  echo "No built frontend found (dist/index.html)."
  echo "Run build.command once before using start.command."
  pause
  exit 1
fi

# Already serving? Just open the browser instead of starting a second copy.
if port_in_use; then
  echo "Noteration already appears to be running. Opening $URL ..."
  open "$URL"
  exit 0
fi

echo "Starting the Noteration server in a new Terminal window..."
# Open a new Terminal window that keeps running so you can read any errors.
osascript >/dev/null 2>&1 <<EOF
tell application "Terminal"
  activate
  do script "cd '$ROOT' && '$PY' -m uvicorn backend.main:app --port $PORT"
end tell
EOF

echo "Waiting for the server to be ready (up to 30s on a cold start)..."
tries=0
while [ "$tries" -lt 30 ]; do
  sleep 1
  if port_in_use; then
    open "$URL"
    echo
    echo "============================================"
    echo "  Noteration is running at $URL"
    echo "  Keep the \"Noteration server\" Terminal window open."
    echo "  Use stop.command when you are done."
    echo "============================================"
    exit 0
  fi
  tries=$((tries + 1))
done

echo
echo "The server did not become ready within 30 seconds."
echo "Look at the new Terminal window for an error message."
echo "If you have not built the app yet, close it and run build.command first."
pause
exit 1
