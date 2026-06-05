#!/usr/bin/env bash
# ============================================================
#  stop.command - shut down the running Noteration server by
#  killing whatever process is listening on the port.
#  (Double-clickable in Finder. macOS equivalent of stop.bat.)
# ============================================================
set -uo pipefail

PORT=8000

pause() { echo; read -n 1 -s -r -p "Press any key to close..."; echo; }

PIDS="$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"

if [ -n "$PIDS" ]; then
  for pid in $PIDS; do
    echo "Stopping Noteration (PID $pid)..."
    kill "$pid" 2>/dev/null || true
  done
  sleep 1
  # Force-kill anything still listening.
  PIDS="$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  [ -n "$PIDS" ] && kill -9 $PIDS 2>/dev/null || true
  echo "Noteration stopped."
else
  echo "Noteration does not appear to be running on port $PORT."
fi

pause
