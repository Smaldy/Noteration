# Noteration — Architecture & Project Documentation

Noteration is a **local-first study app**: a Python (FastAPI) backend that runs an
AI pipeline and serves a built React bundle, persisting everything to a local
SQLite database. It turns lecture PDFs (or recorded audio) into structured notes,
quizzes, and flashcards, and schedules revision with SM-2 spaced repetition.

The organizing constraint is **cost**: the app is built to run free. All AI calls
go through a cheapest-first provider waterfall (Gemini free tier → local Ollama →
paid Claude as an optional last resort), driven by a budget-aware background queue
with a **never-zero-result guarantee** — process what fits the current quota,
commit each topic the moment it finishes, queue the rest with a concrete resume
time. Slow is fine; returning nothing is not.

See [`project-structure.md`](project-structure.md) for the directory-by-directory
layout, and [`../packaging/README.md`](../packaging/README.md) for building the
desktop installers.

---

## How it runs

**From source (dev):**

1. `python -m backend.migrate` creates/upgrades the SQLite DB (Alembic).
2. `npm run build` produces the frontend bundle in `dist/`.
3. `uvicorn backend.main:app` serves the REST API under `/api` and the bundle
   (with an SPA fallback) on `localhost:8000`.

One-click wrappers exist per platform: `WindowsRun/Noteration.bat`,
`MacRun/Noteration.command`, and `scripts/run.ps1` / `scripts/dev.ps1` (build +
migrate + serve + open the browser).

**Packaged (end users):** `packaging/launcher.py` (PyInstaller entry point)
migrates the DB, starts uvicorn on a free localhost port in a thread, waits for
`/api/health`, then opens a native pywebview window — no terminal, no browser
chrome. Runtime data lives outside the install dir (`%LOCALAPPDATA%\Noteration`
on Windows, `~/Library/Application Support/Noteration` on macOS,
`NOTERATION_DATA_DIR` overrides); `backend/paths.py` is the single source of
truth for these paths in both dev and frozen modes.

**Storage:** one SQLite file opened in **WAL mode** with `foreign_keys=ON`
(connect-event PRAGMA). The background queue writes completed topics while the UI
reads concurrently — no writer-blocks-readers stalls. All datetime columns use a
`UTCDateTime` TypeDecorator so timezone-aware UTC survives SQLite round-trips.

---

## Backend

FastAPI app (`backend/main.py`) with thin routers (`backend/routers/`) delegating
to services (`backend/services/`). SQLAlchemy models in `backend/models/`,
Pydantic schemas in `backend/schemas/`, Alembic migrations in
`backend/db/migrations/`. Two background daemons start in the app lifespan: the
generation **worker** and the audio **transcription worker**.

### The pipeline (`services/pipeline/`)

A PDF becomes study material in five stages. The atomic unit of work — and the
DB transaction boundary — is **one topic**, never the whole document, so a limit
hit can never lose meaningful work.

```
PDF ─▶ Ingestion ─▶ Structure ─▶ [user review] ─▶ Queue ─▶ Notes + Assessment ─▶ SM-2 schedule
```

1. **Ingestion** (`ingestion.py`) — `markitdown` converts the PDF to markdown and
   PyMuPDF renders each page to PNG. Both are cached on disk keyed by the file's
   SHA-256 (`cache/<hash>/`), built in a staging dir and atomically swapped in, so
   re-processing never re-pays ingestion and a crash never leaves a half-cache.
   Scanned/no-text PDFs are flagged (`is_scanned`) for the manual-structure path.
2. **Structure detection** (`structure.py`, `pdf_outline.py`) — heuristic only,
   no model call: ATX headings first, then the PDF's embedded outline/bookmarks,
   then a font-size heuristic for heading-less slide decks, then a conservative
   "Chapter N" text fallback. Topmost heading level → chapters, deeper → topics;
   every chapter keeps ≥1 processable topic. The detected tree is recomputed on
   demand and only becomes DB rows when the user **confirms** it in the review
   screen (atomic: chapters + topics + queue jobs + status flip in one
   transaction; re-confirm is refused with 409). Chapters process by default on
   confirm; pausing is opt-in.
3. **Formula vision** (`formula.py`) — math regions are found with a delimiter
   heuristic, registered as `pending` formulas (located, zero model calls), and
   transcribed to LaTeX **lazily, on demand** when the user opens a topic
   (grayscale 150-DPI crops to bound vision tokens). Rendered with KaTeX.
4. **Generation** (`generation.py`) — **one structured-output call per topic**
   returning `{notes_md, mcqs, flashcards}` together (consolidated from an
   earlier two-call design to halve free-tier spend; notes and assessment stay
   mutually consistent). The topic's source text is sliced from the cached
   markdown at generation time (topic heading → chapter section → whole doc —
   never zero context); large books load **per-chapter markdown lazily** to avoid
   context explosion. The `note_length` setting (1–10) scales both the output cap
   and the source window. Notes can be **regenerated on demand** (synchronous,
   with optional user feedback; preserves the quiz/flashcards and their SM-2
   state, refuses locked notes), and more MCQs/flashcards can be generated per
   topic.
5. **Scheduler** (`scheduler.py`) — pure SM-2 core (Correct→5, Incorrect→2 with
   the standard lapse, Skip→inert), materialised into `ScheduleEntry` calendar
   rows per subject. **Deadline mode**: a future `Subject.exam_date` pulls review
   dates forward (`min(interval, days_left)`) without corrupting the stored SM-2
   interval, and appends a revision-buffer window before the exam. Manual
   drag-drop entries and manual calendar events are preserved across rebuilds; an
   AI planner (`planner.py`) can lay out a study plan toward a deadline, skipping
   already-studied topics.

### Provider waterfall (`services/providers/`)

One `Provider` interface (`generate`, `transcribe_image`, `transcribe_audio`,
`budget_probe`) implemented by Gemini (`google-genai`), Claude (`anthropic`),
Ollama (local), and a mock for tests. Nothing outside this layer knows which
model answered.

- **Cheapest-first ordering with automatic failover** (`waterfall.py`): a
  limit-hit cools that provider until its `reset_at` and moves on; hard errors
  get capped exponential backoff; full exhaustion surfaces
  `AllProvidersExhausted(retry_at=…)` so the queue schedules a single wake-up and
  never spins. The waterfall is pure/synchronous (clock injected) — the queue
  owns all waiting.
- **Gemini** holds four free-tier models (2.5/3.5 × flash/flash-lite), each with
  its own RPM/RPD limiter. With rotation ON, a per-model 429 or transient 5xx
  cools just that model and rotates to the next; only when all are limited does
  the tier fail over (typically to Ollama). Rotation, a pinned model, and a
  master Gemini toggle are Settings.
- **Ollama** is the $0 local candidate (model name set in Settings; absence just
  removes it from the waterfall). It never raises a limit error — a local model
  has no quota.
- **Claude** is paid, last resort, and can be hard-disabled (`allow_paid`);
  budget modelled as a rolling ~5h token window.
- **Budgets are modelled locally** (no provider exposes remaining quota): request
  counts and token windows from our own call history, conservative defaults.
- A benchmark harness (`backend/benchmark/`, offline, not part of the served
  app) runs representative topics through providers and scores cost, wall-clock,
  note quality, and formula accuracy to pick the bulk default on evidence.

### Budget-aware queue (`services/queue.py`, `worker.py`)

Persistent jobs (`QueueJob` rows) survive restarts and limit windows. Stages per
topic (formula → notes → assessment, or a reduced set for audio/exam-mode docs)
commit independently and atomically — success writes domain rows + provider
stamp + cost in one transaction; budget exhaustion rolls back and requeues with
a `resume_after`; other failures retry up to `max_attempts`. Orphaned `running`
jobs are recovered to `pending` on startup.

- **Concurrency = one in-flight topic per provider** (a single local model can't
  generate two topics at once), executed on one thread per provider with
  `busy_timeout` so parallel WAL writers wait instead of erroring. Free-tier
  request pacing is enforced per provider.
- **Lanes**: each subject's work runs in a `running` (foreground) or `overnight`
  (background) lane; a foreground lane beats an overnight lane for a contended
  provider. Lanes pause/resume; pausing rolls in-flight jobs back to `queued` so
  the provider frees up immediately.
- **Cost guards**: a per-document token estimate and an optional budget cap stop
  one PDF from burning the daily free quota; headingless-PDF uploads warn before
  enqueueing.
- The queue is the **single writer of topic status** (`queued` / `processing` /
  `ready` / `error`), derived from its jobs inside the same commits.
- A history log records every generation (provider, tokens) for the Queue page's
  History view; provider "active/cooling/disabled" status is derived from live
  config + deferred-job reasons.

### Audio transcription (`services/transcription.py`, `transcription_worker.py`)

Uploading an audio lecture creates a `transcribing` document. Audio is
silence-trimmed and split into ~10-minute chunks at silence boundaries (ffmpeg
via the bundled `imageio-ffmpeg`, fully offline), then transcribed chunk by
chunk with Gemini — **resumably**: finished chunks persist, a rate limit records
a backoff in a `progress.json` sidecar and the worker resumes at the first
missing chunk. The final transcript (markdown with `##` topic headings) enters
the same structure-review → queue → notes flow as a PDF, minus the formula
stage. Transcripts are exportable; users can also attach their own images/audio
to any topic's notes (content-addressed, 25 MB cap).

### Exercise Duplicator (`services/duplicator/`)

An Exam Prep tool (`/duplicator`): upload an exercise PDF → **Stage 1** extracts
each exercise per page with sync vision (JSON: text, dot-notation topic,
difficulty signals, optional viz spec) → **Stage 2** searches university-level
variants per exercise as background `duplicate_search` queue jobs (drained by a
dedicated loop, isolated from the topic/lane hot path) → **Stage 3** renders
visualizations on the frontend (Plotly line/3D plots with pole-breaking and
percentile framing, matter-js physics scenes, SVG force diagrams). A calibration
store (own + imported samples, export/import as JSON) grounds the search prompt
per topic and year level. LaTeX from extraction is normalized client-side
(`features/duplicator/latex.ts`) — delimiter rewriting, bare-command wrapping,
exam-metadata stripping.

### Arcade (`services/arcade.py`, `features/arcade/`)

A study-gated retro minigame ("NOTINVASION") layered non-destructively over the
app: correct MCQs and flashcard reviews earn coins; a run plays over the live,
frozen UI with the cursor as the player, sector navigation through the app's
real routes, bombs to defuse, bosses every 10th wave, and a tiered upgrade shop.
The server is the source of truth for the economy (coins, score, records,
resumable runs, a rolling-1h anti-binge cooldown, 2-continue cap, daily quests);
the client runs a deterministic canvas sim (`features/arcade/game/`: pure
`world.ts` step + `render.ts` draw). A `DEV_MODE` flag (`devMode.ts`) exposes
grant/reset endpoints for testing.

---

## Frontend

React 18 + Vite + TypeScript, feature-based layout (`src/features/<feature>/`),
shadcn/ui primitives on Tailwind v4 (CSS-variable theme, no config file),
Zustand (one store per domain), react-router-dom. Notable pieces:

- **Library** (`/`) — document cards with progress, upload (PDF or audio),
  full-text search, bookmarks, drag-and-drop reordering, transcription status +
  retry.
- **Structure review** (`/documents/:id/review`) — editable chapter/topic tree
  (pure `useReducer`), per-topic priority pills (exam_critical/medium/skip),
  exam date, pre-flight cost estimate.
- **Study view** (`/documents/:id/study/:topicId`) — chapter/topic sidebar +
  three tabs: Notes (react-markdown + KaTeX, TipTap inline editing with a
  Word-style toolbar, attachments, regenerate dialog), Quiz (one MCQ at a time,
  scored), Flashcards (3D flip + self-grade → SM-2 review). Full-screen study
  mode.
- **Queue** (`/queue`) — status cards, expandable per-subject lane cards with
  per-chapter pause/resume, provider strip (active/cooling), resume countdown,
  retry, history view, clear-completed.
- **Calendar** (`/calendar`) — FullCalendar month grid, color-coded by entry
  kind, drag-drop rescheduling, manual events, hourly scheduling, AI plan
  dialog, deadline markers.
- **Exam Prep** (`/exam-prep`, `/exam-practice`, `/duplicator`) — combined
  practice decks and the Exercise Duplicator.
- **Settings** (`/settings`) — API keys (never echoed back; only `*_key_set`
  booleans), provider toggles (Gemini master + rotation/model grid, Ollama
  model, allow-paid), Pomodoro durations, appearance (theme, accent palette that
  re-themes the whole UI via CSS variables, font family/size, live preview).
- **Pomodoro** — floating timer with synthesized ambient sounds (rain/sea) or
  user audio.
- **i18n** — `react-i18next` with en/es/it locales (`src/locales/`).
- **Bundle discipline** — heavy libs (KaTeX, FullCalendar, Plotly, matter-js)
  are async-only manual chunks so the boot bundle stays lean; React stays in the
  eager vendor chunk to avoid init-order hazards.

---

## Data model (`backend/models/`)

Grouped by aggregate, all re-exported from `models/__init__.py`:

- **hierarchy** — `Subject` (top of the tree; owns `exam_date`, the deadline
  driver) → `Document` (file hash = cache key; `source_type` pdf/audio; status
  incl. `transcribing`; page ranges) → `Chapter` (denormalized `subject_id`;
  per-chapter queue state) → `Topic` (priority, status, `studied`, order).
- **content** — `Note` (markdown; `is_manual`/`locked`/`stale`), `Formula`
  (LaTeX, `pending`/`reconstructed`/`verified`, bbox), `MCQ`, `Flashcard`
  (SM-2 fields: ease factor, interval, repetitions, due date), `SourcePage`,
  `NoteAttachment`, `Bookmark`.
- **processing** — `QueueJob` (persistent queue state: stage, attempts,
  `assigned_provider`, `resume_after`, tokens; nullable topic + `exercise_id`
  for search jobs), `ProviderState` (accumulated cost/tokens), `HistoryEvent`.
- **schedule** — `ScheduleEntry` (source `sm2`/`manual`/`deadline`, revision
  buffer, optional hour), manual `CalendarEvent`s.
- **duplicator** — `ExerciseSession` → `ExtractedExercise` → `DuplicateResult`,
  plus `CalibrationSample`.
- **arcade** — `ArcadeState` (singleton), `ArcadeUpgrade`, `ArcadePlaySession`.
- **settings** — singleton `Settings` row (keys, provider flags, Gemini
  rotation/model, Ollama model, note length, token budget, language, Pomodoro,
  appearance).

Enums are Python `StrEnum`s stored as strings (`native_enum=False`). Cascade
delete runs down the Subject→Topic spine and Note→Formula. Alembic is the single
source of truth for schema (`env.py` imports `Base` + engine from the app;
`render_as_batch=True` for SQLite ALTERs).

---

## Design decisions worth knowing

Distilled from the build history; these explain "why is it like this":

- **One call per topic, not two.** The original design generated notes then
  assessment in a second call with the notes as context; on the free tier that
  doubled token spend for no quality gain, so both come from one
  structured-output call.
- **Formula vision is lazy.** Synchronous vision for every equation in the
  background queue was a major cost; regions are only *registered* during
  processing and transcribed when a topic is opened.
- **The queue owns all reliability.** Processors are injected
  `StageProcessor`s that write domain rows uncommitted; the queue owns
  commit/failover/retry/resume. The waterfall never sleeps (clock injected);
  the queue owns wake-ups. This keeps the reliability core deterministic and
  fully testable with fakes — no test touches the network.
- **Search jobs drain separately.** Duplicator `duplicate_search` jobs live in
  `QueueJob` but are excluded from the generation path (no topic/lane logic) and
  drained by their own oldest-first loop — minimal blast radius on the hot path.
- **Per-topic source text is derived, not stored** — sliced from the cached
  markdown at generation time; renamed/merged topics fall back to
  chapter/whole-doc context.
- **SM-2 grade mapping**: a 3-button self-grade carries no latency signal, so
  Correct→5, Incorrect→2 (standard lapse), Skip→no update (deck triage without
  corrupting scheduling state).
- **Secrets** never appear in code, logs, URLs, or API responses (only
  `*_key_set` booleans are echoed). Plaintext keys in the local DB are accepted
  for a single-user local app.
- **Gemini model ids are verified against ListModels, never guessed** — a 404
  on an unserved id once masqueraded as a rate limit and wedged transcription.

## Testing

- **Backend**: `python -m pytest` — ~600 tests (pyproject points pytest at
  `backend/tests/`) covering the queue/provider reliability core, every router,
  the pipeline stages (with a real fixture PDF and real ffmpeg for chunking),
  SM-2, and the duplicator. Tests run on isolated in-memory SQLite
  (StaticPool); provider SDKs are faked — live keys are never needed.
- **Frontend**: `tsc -b` type-checks before `vite build`; there is no JS test
  suite.
- **Packaged app**: `packaging/launcher.py --selftest` (imports every heavy
  dep, checks bundled ffmpeg + frontend, migrates a throwaway DB, exercises the
  real ingest path) and `--smoke` (full launch, auto-close). CI runs the
  selftest inside every built bundle.

## CI / releases

`.github/workflows/` builds the Windows installer (Inno Setup), the macOS
`.dmg` (Apple Silicon), a Linux build, and an Arch package
(`packaging/arch/PKGBUILD`) — each running the bundle's `--selftest` — and
attaches artifacts to GitHub releases on `v*` tags (release notes from
`packaging/RELEASE-NOTES-<version>.md`). The apps ship unsigned; the first-run
OS warnings and click-throughs are documented in
[`packaging/USER-GUIDE.md`](../packaging/USER-GUIDE.md).
