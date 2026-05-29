# CLAUDE.md — Noteration

> Always-on rules, auto-loaded every session. Keep this short (it costs context on
> every load). The full standing build contract is in `RUFLO-BUILD.md`; the
> authoritative spec is in `docs/`.

## Project
Noteration — a local-first, cost-minimizing study app that turns engineering PDFs
into notes, MCQs, flashcards, and an SM-2 schedule. Local web app (FastAPI serving
a React/Vite bundle on localhost). No Tauri.

## Read these
- `RUFLO-BUILD.md` — how to build: wave discipline, checkpoints, resumability.
- `docs/brainstorm-decisions.md` + `docs/cost-strategy.md` — locked decisions; read first.
- `docs/` — full spec (data-model, ai-pipeline, tech-stack, project-structure, ux-flows, review).
- `docs/build-log.md` — current progress; read at the start of every session.

## Non-negotiables
- Don't change locked decisions in `docs/`. Unspecified → check `docs/review.md`
  "Still open", pick the cheapest reasonable option, log it, continue.
- Never fan the whole project out at once. Work in bounded waves; each wave ends at
  a green, committed checkpoint with `docs/build-log.md` updated.
- Every commit is on a compiling/passing tree. The provider layer and queue are the
  reliability core — sequential and test-covered.
- No secrets in code, logs, or URLs.

## Start of every session
Read `docs/build-log.md` → run the build/test check → print a 5-line RESUME
SUMMARY → continue from IN PROGRESS / NEXT. Never restart from scratch or redo DONE.
