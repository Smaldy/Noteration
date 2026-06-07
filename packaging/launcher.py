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


def _selftest() -> int:
    """Headless check that the frozen bundle has every heavy dep + can migrate.

    Run ``Noteration.exe --selftest`` after packaging: it imports the native/
    optional libraries (which PyInstaller most often misses) and applies the
    migrations to a throwaway DB, printing OK or the first failure — no window.
    """
    import importlib
    import os
    import tempfile

    os.environ["NOTERATION_DATA_DIR"] = tempfile.mkdtemp(prefix="noteration_selftest_")
    checks = [
        "pymupdf",
        "fitz",
        "markitdown",
        "imageio_ffmpeg",
        "google.genai",
        "anthropic",
        "uvicorn",
        "webview",
        "backend.main",
    ]
    for name in checks:
        importlib.import_module(name)
        print(f"  import {name}: OK")

    # The static ffmpeg binary (audio transcription) must be bundled, not just
    # the wrapper package.
    import imageio_ffmpeg

    ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    print(f"  ffmpeg -> {ffmpeg.name} ({'exists' if ffmpeg.is_file() else 'MISSING'})")

    # The built frontend bundle must ship with the app.
    from backend.main import FRONTEND_DIST

    index = FRONTEND_DIST / "index.html"
    print(f"  frontend -> {index} ({'exists' if index.is_file() else 'MISSING'})")

    from backend.migrate import run_migrations

    run_migrations()
    from backend.paths import DB_PATH

    print(f"  migrate -> {DB_PATH} ({'exists' if DB_PATH.is_file() else 'MISSING'})")

    # Exercise the real native ingestion path (catches missing markitdown/PyMuPDF
    # data files that a bare import wouldn't): make a 1-page PDF, render it, and
    # convert it to markdown — the two operations every upload depends on.
    import pymupdf
    from markitdown import MarkItDown

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Noteration selftest page.")
    pdf_path = Path(os.environ["NOTERATION_DATA_DIR"]) / "selftest.pdf"
    doc.save(str(pdf_path))
    doc.close()

    rendered = pymupdf.open(str(pdf_path))
    pix = rendered[0].get_pixmap(dpi=72)
    rendered.close()
    md = MarkItDown().convert(str(pdf_path)).text_content
    pipeline_ok = pix.width > 0 and "selftest" in md.lower()
    print(f"  ingest (render+markdown): {'OK' if pipeline_ok else 'FAILED'}")

    if not (ffmpeg.is_file() and index.is_file() and DB_PATH.is_file() and pipeline_ok):
        print("SELFTEST FAILED")
        return 1
    print("SELFTEST OK")
    return 0


def _smoke_seconds() -> float | None:
    """Parse ``--smoke`` / ``--smoke=SECS`` (default 6s) from argv, else None."""
    for arg in sys.argv:
        if arg == "--smoke":
            return 6.0
        if arg.startswith("--smoke="):
            try:
                return float(arg.split("=", 1)[1])
            except ValueError:
                return 6.0
    return None


def _setup_logging() -> None:
    """Route output to a log file in the data dir.

    A windowed (no-console) build can leave ``sys.stdout``/``sys.stderr`` as
    ``None``, so any ``print``/traceback would crash *and* vanish. Writing to
    ``<data dir>/noteration.log`` gives a non-technical user something to send
    when something goes wrong ("attach noteration.log").
    """
    from backend.paths import DATA_DIR

    try:
        log_file = open(DATA_DIR / "noteration.log", "a", buffering=1, encoding="utf-8")
    except OSError:
        return
    if sys.stdout is None:
        sys.stdout = log_file
    if sys.stderr is None:
        sys.stderr = log_file
    print(f"\n--- Noteration launch {time.strftime('%Y-%m-%d %H:%M:%S')} (data: {DATA_DIR}) ---")


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()

    _setup_logging()
    try:
        return _run()
    except Exception:
        import traceback

        traceback.print_exc()
        return 1


def _run() -> int:
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

    window = webview.create_window(
        WINDOW_TITLE, base_url, width=1280, height=860, min_size=(960, 640)
    )

    # `--smoke[=secs]` opens the real window then auto-closes it, so packaging
    # can be verified without a human. Without the flag the window stays open.
    smoke_secs = _smoke_seconds()
    if smoke_secs is not None:
        def _auto_close() -> None:
            time.sleep(smoke_secs)
            print(f"SMOKE: auto-closing window after {smoke_secs}s")
            window.destroy()

        webview.start(_auto_close)
        print("SMOKE OK")
    else:
        # Blocks until the window is closed.
        webview.start()

    # Window closed → stop the server and let the process exit.
    server.should_exit = True
    server_thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
