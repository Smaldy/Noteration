# CLAUDE.md — Noteration

Noteration is a local-first study app. Backend FastAPI + SQLite (WAL) serves a
built React/Vite bundle. Branch `clean-version` is the active line of work.

## Run (dev)

- Backend entry point: `backend.main:app` (uvicorn), default port 8000.
  Auto-runs Alembic migrations on startup and serves `dist/` if it's built —
  there's no separate static host.
- Frontend dev server proxies `/api` to the backend.
- No JS test suite yet — only `backend/tests/` (pytest).
- `NOTERATION_DISABLE_WORKER=1` skips the background workers **and** the
  startup migration — for an isolated/e2e DB, run
  `uv run python -m backend.migrate` first.
- `NOTERATION_DATA_DIR` overrides where the SQLite DB, uploads, and cache
  live.

## Deep reference

`docs/project-structure.md` and `docs/architecture.md` have the full map —
read those for detail. Summary:

**Backend** (`backend/`):
- `main.py` — FastAPI app; mounts `/api` routers + SPA fallback; lifespan
  runs migrate → cache-purge → starts workers (guard via
  `NOTERATION_DISABLE_WORKER=1`).
- `paths.py` — all data paths (dev/frozen/`NOTERATION_DATA_DIR`);
  `UPLOADS_DIR` lives here, not in ingestion.
- `migrate.py` — programmatic `alembic upgrade head`.
- `security.py` — local-origin guard (Host/Origin + nosniff,
  `NOTERATION_EXTRA_HOSTS`).
- `routers/<x>.py` — thin HTTP layer, one per domain, paired with
  `services/<x>.py`.
- `services/<x>.py` — all logic. Key modules: `documents` (upload, structure
  confirm, delete), `topics` (merge), `notes`, `study`, `queue` (budget lane
  queue), `worker` (drain thread), `scheduler` (SM-2), `transcription`
  (+`_worker`), `chat` (AI sidebar engine), `retrieval` (BM25 grounding for the
  sidebar's pinned reference topic).
- `services/pipeline/` — `ingestion` (PDF→md+render, SHA256 disk cache),
  `structure` (3-tier detect) + `pdf_outline` + `slide_grouping`,
  `generation` (one AI call/topic), `formula`, `audio_chunking`,
  `processors` (stage dispatch).
- `services/providers/` — provider `base` ABC, `gemini`, `ollama`,
  `mock`, `waterfall` (Gemini free → Ollama), `budget`
  (limiters), `factory`.
- `models/` — SQLAlchemy ORM by aggregate: `hierarchy`
  (Subject/Document/Chapter/Topic), `content` (Note/MCQ/Flashcard),
  `processing` (QueueJob), `schedule`, `settings`, `chat`
  (ChatSession/ChatMessage), `arcade`, `duplicator`, `enums`.
- `schemas/` — Pydantic request/response models, one file per domain
  (`note.py`, `structure.py`, `subject.py`, …).
- `db/database.py` — engine (WAL + FK pragma) + session factory;
  `db/migrations/` (Alembic); `db/types.py` (`UTCDateTime`).

**Frontend** (`src/`):
- `App.tsx` — router shell.
- `features/<x>/` — one folder per page/domain: library, upload, study,
  queue, calendar, exam, practice, duplicator, settings, arcade, bookmarks,
  search, pomodoro, credits, assistant (docked AI sidebar).
- `components/` — shared UI (`MarkdownView` = markdown+KaTeX,
  `TopicTreeSections`, `ui/` = shadcn primitives).
- `lib/` — `api.ts` (typed fetch), `usePolling`, `useSubjectTopicTree`,
  `providers`, `utils`, `aiContext` (study surfaces → assistant sidebar
  event seam).
- `stores/` — Zustand, one store per domain.
- `locales/` — i18n, `en`/`es`/`it`.

**AI pipeline** (brief): PDF/audio upload → ingest (markdown + page renders,
disk-cached by file hash) → structure detect (embedded outline / AI
slide-grouping / heuristic) → user reviews the proposed tree → confirm
creates Chapter/Topic rows → budget queue → worker drains: one structured AI
call per topic produces notes + quiz + flashcards → SM-2 schedules reviews.
`Topic.pdf_pages` (JSON, 1-indexed) drives per-topic page slicing for
generation. A topic merge re-parents MCQs/cards/attachments and appends
notes under a `## source` heading.

**Data hierarchy & delete semantics:** Subject → Document → Chapter → Topic,
all cascade-deleted downward (`ondelete="CASCADE"` in `models/hierarchy.py`).
`DELETE /api/subjects/{id}` removes a subject and everything under it.
`DELETE /api/documents/{id}` removes one document (and its chapters/topics)
while leaving the parent subject and any sibling documents intact — use this
for "delete this PDF/notes", not the subject endpoint.

## Known gotchas

- pytest swallows its summary line on this Python/pytest combo — trust the
  exit code or grep the collected count instead of reading the tail.
- SQLite is single-writer (WAL mode): never hold a write lock across a
  network round-trip.
- ESLint's compiler-era `react-hooks` rules are deliberately turned off.
