"""Single source of truth for where Noteration writes runtime data.

In dev/test the data lives under ``backend/`` exactly as before, so nothing
changes for the test suite. In a packaged build (PyInstaller sets
``sys.frozen``) the app is installed in a read-only location, so the DB, cache,
and attachments must live in a per-user, writable directory instead:

* Windows  → ``%LOCALAPPDATA%\\Noteration``
* macOS    → ``~/Library/Application Support/Noteration``
* Linux    → ``$XDG_DATA_HOME/Noteration`` (or ``~/.local/share/Noteration``)

``NOTERATION_DATA_DIR`` overrides the choice on any platform (used by the
installer/launcher and handy for support: point it at a clean folder to reset).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _resolve_data_dir() -> Path:
    """Pick the writable root for the DB, cache, and attachments."""
    override = os.environ.get("NOTERATION_DATA_DIR")
    if override:
        return Path(override).expanduser()

    if getattr(sys, "frozen", False):  # running from a PyInstaller bundle
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support"
        else:
            base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        return base / "Noteration"

    # Dev/test: keep the historical layout (files under backend/).
    return Path(__file__).resolve().parent


DATA_DIR = _resolve_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Local SQLite database (one file per install, single writer = the queue).
DB_PATH = DATA_DIR / "noteration.db"

# Hash-keyed ingestion artifacts + original uploads + note attachments.
CACHE_ROOT = DATA_DIR / "cache"
UPLOADS_DIR = CACHE_ROOT / "uploads"
ATTACHMENTS_DIR = CACHE_ROOT / "attachments"
