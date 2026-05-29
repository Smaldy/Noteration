# Project Structure

> Updated: cost-minimizing architecture — provider waterfall, persistent
> budget-aware queue, benchmark harness. Tauri removed (local web app). Frontend
> uses the locked Option A (feature-based) layout.

## Top level — single monorepo

```
noteration/
├── src/                ← React frontend (built bundle served by FastAPI)
├── backend/            ← Python FastAPI (also serves the frontend bundle)
├── docs/               ← planning docs
└── CLAUDE.md
```

## Backend (`backend/`)

```
backend/
├── main.py             ← FastAPI app, router registration, serves frontend bundle
├── routers/            ← HTTP handlers (thin — delegate to services)
│   ├── documents.py
│   ├── topics.py
│   ├── notes.py
│   ├── mcqs.py
│   ├── flashcards.py
│   ├── schedule.py
│   ├── queue.py            (queue status: ready/queued counts, resume time, retry)
│   └── settings.py
├── services/
│   ├── pipeline/       ← one file per pipeline stage
│   │   ├── ingestion.py    (markitdown, page rendering, hash-keyed cache)
│   │   ├── structure.py    (heading/manual detection)
│   │   ├── formula.py      (region crop + vision transcription → LaTeX)
│   │   ├── generation.py   (notes call; MCQs+flashcards call)
│   │   └── scheduler.py    (SM-2 + deadline mode)
│   ├── providers/      ← provider abstraction + cheapest-first waterfall
│   │   ├── base.py         (Provider: generate, transcribe_image, budget_probe)
│   │   ├── gemini.py       (free tier — default)
│   │   ├── claude.py       (paid — last resort; 5h-window budget probe)
│   │   ├── ollama.py       (local $0 — benchmark-gated)
│   │   └── waterfall.py    (ordering, failover, supports_vision routing)
│   ├── queue.py        ← persistent budget-aware worker pool
│   │                     (pre-flight dispatch, commit-per-topic, auto-failover,
│   │                      never-zero-result enforcement)
│   └── cost.py         ← running cost/token estimation per topic
├── models/             ← SQLAlchemy ORM (incl. QueueJob, ProviderState)
├── schemas/            ← Pydantic request/response schemas
├── benchmark/          ← offline harness: Gemini-free vs. Ollama
│   ├── run.py              (runs sample topics through each provider)
│   ├── rubric.py           (note quality + formula accuracy scoring)
│   └── samples/            (representative test topics/PDFs)
├── db/
│   ├── database.py     ← SQLite engine (WAL mode) + session factory
│   └── migrations/     ← Alembic
├── cache/              ← hash-keyed markdown + page renders (gitignored)
└── requirements.txt
```

Key additions for cost control: `services/providers/` (waterfall + failover),
the persistent `services/queue.py`, `services/cost.py`, the `benchmark/` harness,
and the on-disk `cache/`.

## Frontend (`src/`) — Option A: feature-based (locked)

```
src/
├── features/
│   ├── upload/         (file picker, structure review gate)
│   ├── study/
│   │   ├── notes/      (TipTap editor, formula annotations, regenerate+diff)
│   │   ├── quiz/       (MCQ view)
│   │   └── flashcards/ (card flip + SM-2 self-grade)
│   ├── calendar/       (FullCalendar + Pomodoro top-bar timer)
│   ├── queue/          (ready/queued counts, resume countdown, retry failed)
│   └── settings/       (provider order, allow-paid switch, keys, appearance)
├── components/
│   └── ui/             (shadcn/ui primitives)
├── stores/             (Zustand — one store per domain)
├── hooks/              (usePomodoro, useQueue, ...)
├── lib/
│   ├── api.ts
│   └── utils.ts
├── types/
└── App.tsx
```

A dedicated `features/queue/` surfaces the never-zero-result state to the student:
what's ready to study now, what's waiting, and when it resumes.
