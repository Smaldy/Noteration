# Tech Stack

> Updated for cost minimization (see `cost-strategy.md`): a cheapest-first
> provider waterfall with a budget probe, Ollama as a local $0 candidate, and a
> benchmark harness to decide free-tier vs. local on evidence. Also: Tauri dropped
> (local web app), SQLite WAL mode. Items marked `<!-- inferred -->` are reconstructed.

## Shape: local web app

Noteration ships as a **local web app**, not a desktop binary. The Python backend
serves the built React bundle; the user opens it in their browser at `localhost`.
No Rust shell, no sidecar, no packaging step.

## Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python + FastAPI | Pipeline, budget-aware queue, AI calls, serves frontend |
| Frontend | React + Vite | UI, study views, calendar |
| Editor | TipTap | Inline markdown note editing |
| Animation | Framer Motion | Flashcard flips, transitions |
| Calendar | FullCalendar | Month/week grid, drag-drop scheduling |
| UI primitives | shadcn/ui | Buttons, dialogs, form controls <!-- inferred --> |
| State | Zustand | One store slice per domain |
| Storage | SQLite (**WAL mode**) | Local-first persistence |
| ORM | SQLAlchemy | Models mirroring the data model |
| Migrations | Alembic | Schema versioning |
| Ingestion | markitdown | PDF → markdown (cached) |
| PDF rendering | PyMuPDF (fitz) | Render pages / crop formula regions |
| AI | Provider waterfall (see below) | Generation + vision behind one interface |

## SQLite in WAL mode

Open the database with `PRAGMA journal_mode=WAL`. The background queue writes
completed topics while the UI reads concurrently — no writer-blocks-readers
stalls. Correct for a local app with one writer (the queue) and frequent reads,
and it makes the never-zero-result guarantee cheap: each topic commits the instant
it finishes without contending with the UI.

## Provider abstraction + waterfall (day one)

One `Provider` interface, implemented by every backend, exposing:

```
generate(prompt, max_tokens, ...)   → text
transcribe_image(image, ...)        → text (vision)
budget_probe()                      → { headroom, reset_at, supports_vision }
```

No code outside the provider layer knows which model is active. The queue tries
providers in **cheapest-first** order and fails over automatically on a limit-hit:

```
1. Gemini free tier   ($0, quota-limited)        ← default
2. Other free tier    ($0)                         <!-- inferred: which -->
3. Ollama local       ($0, slow, hardware-bound)   ← benchmark-gated
4. Paid Claude        (last resort, costs money; can be hard-disabled)
```

`budget_probe()` is what lets the queue dispatch only what fits and queue the
rest (see `cost-strategy.md`). `supports_vision` lets the formula stage pick a
vision-capable provider instead of failing at call time.

## Ollama (local, $0) — candidate

Ollama runs an open model locally for $0 and no quota, trading speed for cost.
It's a first-class candidate in the waterfall but **benchmark-gated**: it's only
adopted as the bulk default if it clears the quality bar (notes + formula
accuracy) at acceptable wall-clock time. Requires the user to have it installed;
absence just removes it from the waterfall.

## Benchmark harness

A small offline script (not part of the served app) runs the same representative
topics through Gemini-free and Ollama and records cost, wall-clock time, note
quality (rubric), formula accuracy, and throughput-before-limit. Output decides
the default bulk provider. Re-run when models change. Lives at
`backend/benchmark/` (see `project-structure.md`).

## How it runs

1. `uvicorn` starts FastAPI.
2. FastAPI serves the built React bundle and the REST API on `localhost`.
3. The browser opens the app; all reads/writes go to the local SQLite file.
4. The queue processes topics in the background within free-tier budgets,
   committing each as it completes.

## Deferred

- Cloud sync (schema designed to export cleanly when added).
- Any desktop packaging.
