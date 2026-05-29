# Build Log — Noteration

> Human-readable progress truth, per `RUFLO-BUILD.md`. Updated at every wave
> checkpoint. Read this first at the start of every session.

## DONE

- **Phase 1 — Scaffold (Wave 1)** — Monorepo per `project-structure.md`:
  Vite + React + TS frontend (`src/`) built to `dist/`; FastAPI (`backend/`)
  serving the API under `/api` and the built bundle with SPA fallback for
  everything else; SQLite engine in WAL mode + session factory
  (`backend/db/database.py`); Alembic wired (`backend/alembic.ini`,
  `backend/db/migrations/`, env imports Base+engine from the app); health
  endpoint `GET /api/health` with a passing test (`backend/tests/test_health.py`).
  Tree green: `pytest` 1 passed, `npm run build` clean, WAL verified, serving
  verified end-to-end (API + `/` + SPA route).
- **Phase 1 — Audit + fix (Wave 1b)** — Reviewed the scaffold. Fixed a routing
  defect: when the bundle is mounted, the SPA catch-all swallowed unknown
  `/api/*` paths, returning `200` + index.html instead of a JSON `404` (would
  feed HTML to `fetch()` and break `JSON.parse`). Catch-all now 404s any
  unmatched `/api/*`; `/docs` + `/openapi.json` confirmed unaffected. Added a
  regression test. Tree green: `pytest` 2 passed.

## IN PROGRESS

- (none — Wave 1 checkpoint committed)

## NEXT

1. **Phase 2 — Data model** — SQLAlchemy models exactly per `docs/data-model.md`
   (Subject → Chapter → Topic hierarchy, `QueueJob`, `ProviderState`, SM-2
   fields, denormalized `Chapter.subject_id`). One Alembic migration
   (`alembic revision --autogenerate`). Per-table tests. Import model modules
   in `backend/models/__init__.py` so autogenerate sees them.
2. **Phase 3 — Provider layer** (reliability core, TDD, sequential): `base.py`
   interface, mock provider, Gemini/Claude/Ollama stubs, `waterfall.py`
   (cheapest-first, failover, single-wake-up backoff). Test failover.
3. **Phase 4 — Persistent queue** (reliability core, TDD, sequential):
   topic-atomic transactions, pre-flight budget dispatch, priority ordering,
   sub-stage commits, resume-from-DB. Mid-job-limit + restart test.
4. Phases 5–11 per `RUFLO-BUILD.md` build order.

## DECISIONS

- **Frontend language = TypeScript.** Locked stack says React + Vite; TS is the
  standard pairing and is required by shadcn/ui (locked UI primitives). Build
  script type-checks (`tsc --noEmit`) before `vite build`.
- **Serving model.** FastAPI mounts the built `dist/` (StaticFiles for
  `/assets`, catch-all → `index.html` for SPA routes); API lives under `/api`
  and is registered first so it always wins. Bundle is optional at runtime
  (absent in dev/test); dev uses Vite's `/api` proxy to `localhost:8000`.
- **DB location.** Single SQLite file at `backend/noteration.db` (gitignored).
  WAL + `foreign_keys=ON` set via a connect-event PRAGMA on every connection.
- **Alembic single-source-of-truth.** `env.py` imports `Base` and the engine
  from `backend.db.database` rather than duplicating the URL in `alembic.ini`;
  `render_as_batch=True` so SQLite ALTERs work in later phases.
- **Lean install.** Only Phase-1 deps in `backend/requirements.txt`
  (fastapi, uvicorn, sqlalchemy, alembic, pydantic[-settings], pytest, httpx);
  pipeline/provider deps (markitdown, pymupdf, provider SDKs) are added in their
  own phases to keep the tree green and installs fast.
- **Toolchain (this machine):** Python 3.14.5 (venv at repo-root `.venv`),
  Node 24.16, npm 11.13. All Phase-1 deps have cp314 wheels.

## BLOCKED

- (none)

## NOTES / WATCH

- `StarletteDeprecationWarning`: TestClient suggests `httpx2`. Cosmetic; revisit
  if it becomes noisy. Not a blocker.
- The four "Still open" items in `docs/review.md` (Ollama model, equation
  detector, SM-2 grade mapping, second free tier) are decided in their relevant
  phases (3–4, 7–8), not now.
