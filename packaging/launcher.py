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

import os
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
        "ollama",  # local provider — imported lazily, so easy to miss in the freeze
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

    # The built frontend bundle must ship with the app — and not just the HTML
    # shell: a truncated build with index.html but no assets/ would serve a blank
    # window. Assert the emitted JS and the bundled fonts are actually present.
    from backend.main import FRONTEND_DIST

    index = FRONTEND_DIST / "index.html"
    assets = FRONTEND_DIST / "assets"
    js_files = list(assets.glob("*.js")) if assets.is_dir() else []
    font_files = list(assets.glob("*.woff2")) if assets.is_dir() else []
    frontend_ok = index.is_file() and bool(js_files) and bool(font_files)
    print(
        f"  frontend -> {index.name} + {len(js_files)} js, {len(font_files)} fonts "
        f"({'OK' if frontend_ok else 'INCOMPLETE'})"
    )

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

    if not (ffmpeg.is_file() and frontend_ok and DB_PATH.is_file() and pipeline_ok):
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


def _redirect_std_if_detached(path: str | None) -> None:
    """Guarantee ``sys.stdout``/``sys.stderr`` are writable before the selftest.

    The shipped build is windowed, and on Windows a windowed PyInstaller app
    detaches the standard streams — they come back as ``None``. ``_selftest``
    prints as it goes, so that first ``print`` would raise ``AttributeError``
    and the process would exit non-zero before running a single check (which is
    exactly why the frozen ``--selftest`` failed on Windows with no output).
    macOS/Linux keep the streams attached, so this is a no-op there.

    Prefer a caller-supplied log path (CI points ``NOTERATION_SELFTEST_LOG`` at
    a file it reads back for diagnostics); fall back to devnull so a bad path
    can never turn a healthy build red.
    """
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        stream = (
            open(path, "a", buffering=1, encoding="utf-8")
            if path
            else open(os.devnull, "w", encoding="utf-8")
        )
    except OSError:
        stream = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


def main() -> int:
    if "--selftest" in sys.argv:
        _redirect_std_if_detached(os.environ.get("NOTERATION_SELFTEST_LOG"))
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

    from backend.paths import DATA_DIR

    window = webview.create_window(
        WINDOW_TITLE, base_url, width=1280, height=860, min_size=(960, 640)
    )

    # pywebview defaults to private mode, and WebKitGTK's ephemeral context has
    # *no* localStorage at all — any page that reads it throws and unmounts the
    # app. A persistent profile in the data dir gives every platform working
    # localStorage/IndexedDB (pomodoro custom sound, per-page UI prefs).
    webview_profile = {
        "private_mode": False,
        "storage_path": str(DATA_DIR / "webview"),
    }

    # `--smoke[=secs]` opens the real window then auto-closes it, so packaging
    # can be verified without a human. Without the flag the window stays open.
    smoke_secs = _smoke_seconds()
    if smoke_secs is not None:
        def _auto_close() -> None:
            time.sleep(smoke_secs)
            print(f"SMOKE: auto-closing window after {smoke_secs}s")
            window.destroy()

        webview.start(_auto_close, **webview_profile)
        print("SMOKE OK")
    else:
        # Blocks until the window is closed.
        webview.start(**webview_profile)

    # Window closed → stop the server and let the process exit.
    server.should_exit = True
    server_thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
