# Dev commands cheat sheet

Personal reference for building, running, and checking Noteration by hand.
Written for a human at the keyboard, not for an AI assistant — nothing here
needs to be read before making a code change.

All commands assume you're in the repo root (`~/Noteration`) unless noted.

## 1. First-time setup (once per machine)

You need Node.js (v22) and `uv` (a fast Python package/environment manager —
https://docs.astral.sh/uv/getting-started/installation/) installed.

```bash
# Backend: create the virtual environment and install its dependencies
uv venv
uv pip install -r backend/requirements.txt

# Frontend: install its dependencies
npm install
```

## 2. Day-to-day development

Run these in two separate terminals, both from the repo root.

```bash
# Terminal 1 — backend API (auto-reloads the DB schema on start)
uv run uvicorn backend.main:app --port 8000

# Terminal 2 — frontend dev server (hot-reloads on save)
npm run dev
```

The frontend dev server prints a `localhost` URL — open that one in your
browser while developing (it talks to the backend automatically). Stop
either with `Ctrl+C`.

## 3. Build for production-style testing

This is what actually ships: a compiled frontend served *by* the backend, no
separate dev server involved.

```bash
npm run build                                       # builds src/ -> dist/
uv run uvicorn backend.main:app --port 8000          # serves dist/ directly
```

Then open `http://localhost:8000` in a browser.

## 4. Database migrations

Normally automatic — the backend applies any pending migration every time it
starts. To apply them by hand (e.g. before running scripts that touch the DB
directly):

```bash
uv run python -m backend.migrate
```

## 5. Checks before committing

```bash
# Backend
uv run pytest backend/tests/          # run the test suite
uv run ruff check backend             # lint

# Frontend
npm run lint                          # eslint
npm run build                         # type-checks (tsc) AND builds — fails on type errors
```

If all four are clean, you're safe to commit.

## 6. Quick manual smoke test

```bash
curl localhost:8000/api/health        # should print {"status":"ok"}
```

Then click through the app in a browser: upload a PDF, confirm its
structure, open a topic, and check notes/quiz/flashcards generate.

## 7. Building the installers (release only)

This is a separate, heavier process (PyInstaller + Inno Setup for Windows;
GitHub Actions for macOS). Full steps are in `packaging/README.md` — don't
duplicate them here, that file is kept current with the packaging setup.
