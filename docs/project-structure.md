# Project Structure

How the repository is laid out and what each piece is for. See
[`architecture.md`](architecture.md) for how the pieces work together.

## Top level

```
Noteration/
├── backend/            ← Python FastAPI app (pipeline, queue, AI calls; serves the frontend)
├── src/                ← React frontend (built to dist/, served by the backend)
├── packaging/          ← desktop packaging: launcher, PyInstaller spec, installers, user guide
├── docs/               ← project documentation (this file + architecture.md)
├── scripts/            ← PowerShell dev/run helpers + README screenshots (shots/)
├── WindowsRun/         ← one-click .bat launchers (build/start/stop) for running from source
├── MacRun/             ← one-click .command launchers (macOS equivalent)
├── .github/workflows/  ← CI: Windows/macOS/Linux/Arch installer builds + release uploads
├── index.html          ← Vite entry HTML
├── package.json        ← frontend deps + scripts (build = tsc -b && vite build)
├── vite.config.ts      ← Vite config (@ alias, /api dev proxy, manual chunks)
├── tsconfig*.json      ← TypeScript configs
├── components.json     ← shadcn/ui CLI config
├── pyproject.toml      ← pytest config (testpaths = backend/tests)
└── README.md
```

## Backend (`backend/`)

```
backend/
├── main.py             ← FastAPI app: routers under /api, SPA fallback, lifespan starts workers
├── paths.py            ← single source of truth for data paths (dev vs frozen vs NOTERATION_DATA_DIR)
├── migrate.py          ← programmatic `alembic upgrade head`
├── alembic.ini
├── requirements.txt
├── routers/            ← thin HTTP handlers, one per domain (documents, topics, notes,
│                         study, queue, settings, subjects, chapters, search, bookmarks,
│                         assessment, attachments, arcade, duplicator)
├── schemas/            ← Pydantic request/response models, mirroring the routers
├── services/           ← all business logic
│   ├── pipeline/       ← ingestion, structure + pdf_outline, formula, generation,
│   │                     audio_chunking, processors (stage dispatcher)
│   ├── providers/      ← base ABC, gemini, claude, ollama, mock, waterfall,
│   │                     budget (limiters), factory
│   ├── duplicator/     ← extraction, search, sessions, calibration
│   ├── queue.py        ← persistent budget-aware queue (lanes, stages, atomic commits)
│   ├── worker.py       ← background drain loop (one thread per provider)
│   ├── transcription.py / transcription_worker.py   ← resumable audio → transcript
│   ├── scheduler.py    ← pure SM-2 + deadline mode
│   ├── planner.py      ← AI study-plan generation
│   └── …               ← documents, topics, notes, study, settings, subjects,
│                         search, bookmarks, attachments, assessment, arcade,
│                         history, queue_view
├── models/             ← SQLAlchemy ORM, grouped by aggregate: hierarchy, content,
│                         processing, schedule, settings, arcade, duplicator, enums
├── db/
│   ├── database.py     ← SQLite engine (WAL + foreign_keys PRAGMA), session factory
│   ├── types.py        ← UTCDateTime TypeDecorator
│   └── migrations/     ← Alembic env + versioned migrations
├── benchmark/          ← offline provider quality/cost harness (not part of the app)
├── tests/              ← pytest suite (~600 tests; in-memory SQLite, faked providers)
└── cache/              ← runtime: hash-keyed markdown/page renders, uploads, attachments (gitignored)
```

## Frontend (`src/`)

Feature-based layout: each feature owns its pages and components.

```
src/
├── main.tsx / App.tsx  ← router shell (lazy routes), boot-time settings fetch
├── index.css           ← Tailwind v4 theme (CSS variables), global styles
├── features/
│   ├── library/        ← home: document cards, status, upload entry
│   ├── upload/         ← upload dialog + structure-review page (reducer-driven tree)
│   ├── study/          ← study page: sidebar + Notes/Quiz/Flashcards tabs, regenerate
│   ├── editor/  (components/editor) ← TipTap note editor + toolbar
│   ├── queue/          ← queue page: lanes, provider strip, history
│   ├── calendar/       ← FullCalendar page, manual events, AI plan dialog
│   ├── exam/           ← exam prep + practice pages
│   ├── duplicator/     ← exercise duplicator page, renderers/ (Plotly, matter-js,
│   │                     force diagrams), latex.ts normalization
│   ├── bookmarks/      ← bookmarks page + button
│   ├── search/         ← full-text search bar
│   ├── settings/       ← settings page (keys, providers, appearance)
│   ├── pomodoro/       ← floating timer + synthesized audio
│   ├── practice/       ← topic-select dialog for combined decks
│   ├── arcade/         ← the minigame: cabinet UI, game/ (pure sim + canvas render)
│   └── credits/        ← credits overlay
├── components/
│   ├── ui/             ← shadcn/ui primitives (button, card, dialog, tabs, …)
│   ├── MarkdownView.tsx ← shared markdown + KaTeX renderer
│   └── TimeWheel.tsx
├── stores/             ← Zustand stores, one per domain (library, study, queue, …)
├── lib/                ← api.ts (typed fetch wrapper), providers.ts, utils.ts, arcadeEvents.ts
├── types/              ← TS mirrors of the API schemas
├── i18n/ + locales/    ← react-i18next setup; en / es / it translations
└── vite-env.d.ts
```

## Packaging (`packaging/`)

```
packaging/
├── launcher.py             ← desktop entry point (migrate → uvicorn → pywebview window);
│                             --selftest and --smoke verification modes
├── noteration.spec         ← PyInstaller recipe (bundles dist/, migrations, native deps)
├── installer.iss           ← Inno Setup script (per-user Windows installer)
├── requirements-build.txt  ← build-only deps (pyinstaller, …)
├── make_icon.py            ← regenerates assets/noteration.{ico,icns,png}
├── assets/                 ← app icons
├── arch/                   ← Arch Linux PKGBUILD + .desktop file
├── README.md               ← developer packaging guide (build/verify/release)
├── USER-GUIDE.md           ← non-technical install & first-use guide (shipped in the installer)
└── RELEASE-NOTES-<ver>.md  ← release notes attached to GitHub releases by CI
```
