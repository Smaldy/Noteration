# PyInstaller spec for Noteration — builds the native desktop app.
#
#   Windows / macOS:  pyinstaller packaging/noteration.spec
#
# One-folder build (faster startup, easier for the installer to lay down than a
# single self-extracting exe). Output: dist/Noteration/ (+ Noteration.app on mac).
#
# Set NOTERATION_BUILD_CONSOLE=1 to keep a console window for debugging the
# frozen app; unset (default) hides it for delivery.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent  # SPECPATH = packaging/ ; ROOT = repo root

datas = []
binaries = []
hiddenimports = []

# Heavy / data-bearing packages PyInstaller often under-collects. magika ships
# an ML model dir that markitdown loads for file-type detection on every convert.
for pkg in ("markitdown", "magika", "imageio_ffmpeg", "pymupdf"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# Dynamically-imported submodules: uvicorn protocol/loop autodetect, alembic
# DDL impls, and every backend module (routers/services loaded via factories).
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("alembic")
hiddenimports += [
    m
    for m in collect_submodules("backend")
    if not m.startswith(("backend.tests", "backend.benchmark"))
]
hiddenimports += ["fitz"]  # pymupdf legacy alias used by some code paths

# TLS roots for the AI SDK HTTP clients.
datas += collect_data_files("certifi")

# Linux: pywebview uses the GTK/WebKit backend via PyGObject (`gi`), which is
# imported lazily (so PyInstaller's static analysis misses it). Pull it in plus
# the GTK backend module. The host still needs the system WebKit2GTK runtime
# (libwebkit2gtk-4.1) — we bundle the Python bindings, not the GTK stack itself.
if sys.platform.startswith("linux"):
    for pkg in ("gi", "cairo"):
        try:
            d, b, h = collect_all(pkg)
            datas += d
            binaries += b
            hiddenimports += h
        except Exception:
            pass
    hiddenimports += ["webview.platforms.gtk", "gi.repository.WebKit2", "gi.repository.Gtk"]

# App payload: the built frontend bundle and the Alembic migration scripts.
# Targets chosen so the running code finds them:
#   backend/main.py    -> <bundle>/dist
#   backend/migrate.py -> <bundle>/backend/db/migrations
datas += [
    (str(ROOT / "dist"), "dist"),
    (str(ROOT / "backend" / "db" / "migrations"), "backend/db/migrations"),
]

console = os.environ.get("NOTERATION_BUILD_CONSOLE") == "1"

icon_win = ROOT / "packaging" / "assets" / "noteration.ico"
icon_mac = ROOT / "packaging" / "assets" / "noteration.icns"
icon = None
if sys.platform == "win32" and icon_win.is_file():
    icon = str(icon_win)
elif sys.platform == "darwin" and icon_mac.is_file():
    icon = str(icon_mac)

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Noteration",
    debug=False,
    strip=False,
    upx=False,
    console=console,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Noteration",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Noteration.app",
        icon=icon,
        bundle_identifier="com.noteration.app",
        info_plist={
            "CFBundleName": "Noteration",
            "CFBundleDisplayName": "Noteration",
            "CFBundleShortVersionString": "0.3.0",
            "CFBundleVersion": "0.3.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
