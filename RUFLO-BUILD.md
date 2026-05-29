# Noteration — Ruflo Build Contract

> The standing "how to build" rules for the Ruflo swarm. `CLAUDE.md` (auto-loaded)
> points here. The authoritative spec is `docs/`. This file is named so Ruflo's
> `init` won't overwrite it — do not rename it to `CLAUDE.md`.

## Source of truth
`docs/` is authoritative. Read `brainstorm-decisions.md` and `cost-strategy.md`
first; consult the others per phase. **Don't re-derive or change locked
decisions.** Unspecified → `docs/review.md` "Still open": pick the cheapest
reasonable option, log under `## DECISIONS` in `docs/build-log.md`, continue. Only
a true contradiction blocks you — write it under `## BLOCKED` and stop.

## Use the swarm — with discipline
Use Ruflo's coordination fully (hive-mind, parallel agents, shared memory). These
rules keep the swarm from reintroducing the failure we're guarding against — a big
fan-out that burns the session and leaves a broken tree:

- **Bounded waves, not one giant graph.** Spawn agents for the current phase's
  parallelizable tasks only (a handful at a time). Finish and checkpoint a wave
  before planning the next. Keep topology tight (hierarchical / queen-led) so a
  coordinator owns ordering and integration.
- **One writer for commits.** Workers produce changes; the queen integrates and
  commits to a green tree. Partition work by file/module so parallel agents don't
  collide or commit concurrently to the same area.
- **Checkpoint barrier after every wave.** Integrate → green tree → commit →
  update `docs/build-log.md`. Each barrier is a safe stop; assume the session can
  end abruptly at any one.
- **Respect dependencies.** Don't parallelize across the reliability core (phases
  3–4); the provider layer and queue are sequential and test-gated. Parallelize
  within a phase only where tasks are truly independent (several frontend features,
  several routers).

## Session limit (Pro, 5-hour windows)
Quota-limited, not money-limited. I watch usage via `/status` and `/usage`; don't
estimate context % (you can't measure it reliably). Parallel agents spend the
window faster, so **wave size is the throttle** — keep each wave small enough to
complete and checkpoint within a session. On "wrap up": halt new spawns, let
in-flight work finish or roll back cleanly, integrate to green, commit, update the
log, stop.

## Resumability — `docs/build-log.md` is the contract
Human-readable progress truth, kept current by the coordinator at every barrier:
```
## DONE        (completed tasks/waves — one line each, newest last)
## IN PROGRESS (current wave: which tasks/agents, exact next step each)
## NEXT        (ordered queue of upcoming tasks/waves)
## DECISIONS   (choices for open questions, one-line rationale)
## BLOCKED     (questions needing me; empty = unblocked)
```
Let Ruflo's own cross-session memory handle agent-side recall — don't duplicate it
with manual memory writes unless something genuinely won't fit here.

**Start of every session, before spawning agents:** read `docs/build-log.md` → run
the build/test check → print a 5-line RESUME SUMMARY (last done · current state ·
next wave · blockers · green/red) → continue from IN PROGRESS → NEXT. Never restart
or redo DONE. Every task ends green before commit; an unavoidable broken commit is
tagged `WIP-BROKEN` with the fix as the first NEXT item.

## Build order
Layout per `project-structure.md` (local web app, no Tauri). Smallest tasks first,
checkpoint after each wave. Don't start AI features before skeleton + persistence
are green.

1. **Scaffold** — monorepo; FastAPI serving a Vite/React bundle on localhost;
   SQLite `PRAGMA journal_mode=WAL`; Alembic; health endpoint + one passing test.
2. **Data model** — models exactly per `data-model.md` (incl. `QueueJob`,
   `ProviderState`, SM-2 fields); one migration; per-table tests.
3. **Provider layer** — `base.py` (`generate`, `transcribe_image`, `budget_probe`,
   `supports_vision`); mock provider for tests; Gemini/Claude/Ollama stubs;
   `waterfall.py` (cheapest-first, failover, single-wake-up backoff). Test failover.
4. **Persistent queue (reliability core — test-covered)** — topic = atomic unit;
   per-topic transaction commit; pre-flight dispatch by probed headroom; priority
   ordering; sub-stage commits; resume-from-DB on startup. Include a mid-job-limit +
   restart test proving no work is lost and nothing is half-written.
5. **Ingestion** — markitdown + PyMuPDF renders + `file_hash` cache + cache-check;
   tiny fixture PDF test.
6. **Structure detection + review API** — heading detection + manual fallback.
7. **Generation + formula vision** — notes call; MCQs+flashcards call (notes as
   context); detect-then-crop vision, exam-critical first, confidence stored.
8. **Scheduler** — SM-2 + deadline mode.
9. **Frontend (feature-based, Option A)** per `ux-flows.md`, one feature
   end-to-end at a time: Library → Upload/Structure Review → Study View → Calendar
   → Queue screen → Settings.
10. **Cost UX (priority)** — live spend readout, pre-flight estimate, overnight
    mode, per-document trust banner, provider stamping surfaced.
11. **Benchmark harness** — `backend/benchmark/`, Gemini-free vs. Ollama on the
    3060-laptop baseline; output stored as config the waterfall reads.

## Standards
Follow `tech-stack.md` exactly. TDD for the queue and waterfall (phases 3–4). Thin
routers, logic in services. Small, single-concern commits.
