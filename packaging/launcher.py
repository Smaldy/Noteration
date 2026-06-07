"""Desktop entry point for Noteration — the thing the user's shortcut runs.

No terminal, no browser chrome. It:

1. Migrates the per-user database to ``head`` (creates it on first run).
2. Starts the FastAPI app (uvicorn) on a free localhost port, in a thread.
3. Waits until the server answers ``/api/health``.
4. Opens a native window (pywebview: WebView2 on Windows, WebKit on macOS)
   pointed at the local app.
5. Shuts the server down cleanly when the window is closed.

Runs the same in dev (``python packaging/launcher.py``) and frozen (PyInstaller
sets ``sys.frozen``); ``backend.paths`` decides where data lives in each case.
"""

from __future__ import annotations

import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

# When run as a loose script in dev, make the repo root importable so
# ``import backend`` works. In a frozen bundle the package is already on path.
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HOST = "127.0.0.1"
WINDOW_TITLE = "Noteration"


def _find_free_port() -> int:
    """Ask the OS for an unused localhost port (avoids a hardcoded clash)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def _wait_for_health(url: str, timeout: float = 30.0) -> bool:
    """Poll ``/api/health`` until the server is ready (or we give up)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.15)
    return False


def main() -> int:
    # Bring the database up to date before anything serves it.
    from backend.migrate import run_migrations

    run_migrations()

    port = _find_free_port()
    base_url = f"http://{HOST}:{port}"

    import uvicorn

    from backend.main import app

    config = uvicorn.Config(app, host=HOST, port=port, log_level="warning")
    server = uvicorn.Server(config)
    # uvicorn skips signal handlers off the main thread; serving in a thread lets
    # the GUI own the main thread (required by pywebview on macOS).
    server_thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    server_thread.start()

    if not _wait_for_health(f"{base_url}/api/health"):
        server.should_exit = True
        print("Noteration failed to start (server did not become healthy).", file=sys.stderr)
        return 1

    import webview

    webview.create_window(WINDOW_TITLE, base_url, width=1280, height=860, min_size=(960, 640))
    # Blocks until the window is closed.
    webview.start()

    # Window closed → stop the server and let the process exit.
    server.should_exit = True
    server_thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
