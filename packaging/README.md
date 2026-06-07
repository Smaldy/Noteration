# Packaging Noteration for delivery

Turns the repo into a double-click desktop app for non-technical users — a native
window (no terminal, no browser chrome), bundled with its own Python so the
recipient installs nothing.

| Platform | Output | Built where |
|---|---|---|
| Windows | `Noteration-Setup-<ver>.exe` (Inno Setup installer) | locally, on Windows |
| macOS | `Noteration-macOS.dmg` (drag to Applications) | GitHub Actions (`.github/workflows/build-macos.yml`) |

The app is **unsigned**, so first launch shows an OS warning — see
[`USER-GUIDE.md`](USER-GUIDE.md) for the click-through.

## How it fits together

- `launcher.py` — the entry point the shortcut runs: migrates the DB → starts
  uvicorn on a free localhost port in a thread → waits for `/api/health` → opens a
  pywebview window → clean shutdown on close. Logs to `<data dir>/noteration.log`.
- `noteration.spec` — PyInstaller recipe (one-folder). Collects the heavy native
  deps (PyMuPDF, markitdown + its magika model, the imageio-ffmpeg binary, the AI
  SDKs) and bundles the built frontend `dist/` + the Alembic migrations.
- `installer.iss` — Inno Setup script: per-user install (no admin), shortcuts,
  uninstaller (keeps user data, with an opt-in wipe).
- `make_icon.py` — regenerates `assets/noteration.{ico,icns,png}`.
- Runtime data (DB, cache, attachments, log) lives **outside** the install dir, in
  a per-user folder, so updates/uninstall never touch the user's notes:
  - Windows: `%LOCALAPPDATA%\Noteration`
  - macOS: `~/Library/Application Support/Noteration`
  - override with `NOTERATION_DATA_DIR`.

## Build the Windows installer

```powershell
# from the repo root, in the build venv
npm ci; npm run build                                   # produces dist/
pip install -r backend/requirements.txt
pip install -r packaging/requirements-build.txt

pyinstaller packaging/noteration.spec --noconfirm `
  --distpath packaging/dist --workpath packaging/build  # -> packaging/dist/Noteration/
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\installer.iss
# -> packaging/installer_output/Noteration-Setup-<ver>.exe
```

Set `NOTERATION_BUILD_CONSOLE=1` before `pyinstaller` to keep a console window
for debugging the frozen app.

## Verify a build (no human needed)

```powershell
packaging\dist\Noteration\Noteration.exe --selftest   # imports + ingest + migrate
packaging\dist\Noteration\Noteration.exe --smoke=6     # opens the real window 6s
```

`--selftest` imports every heavy dependency, checks the bundled ffmpeg binary and
frontend, applies migrations to a throwaway DB, and runs a real PyMuPDF render +
markitdown→markdown — catching missing data files that a bare import wouldn't.

## Build the macOS .dmg

Push to `main`/`delivery-ready` (or run the workflow manually). CI builds the
`.app`, runs `--selftest` on it, packages the `.dmg`, and uploads it as an
artifact; tagging `v*` also attaches it to the GitHub release. arm64 only for now
(Apple-Silicon Macs); add a `macos-13` matrix job for Intel.

## Release

```bash
git tag v0.1.0 && git push --tags     # CI attaches the .dmg to the release
```
Upload the Windows `Noteration-Setup-<ver>.exe` to the same release.
