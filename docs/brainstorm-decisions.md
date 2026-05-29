# Brainstorm Decisions

> Locked product decisions and resolved questions for **Noteration** — a
> local-first, **cost-minimizing** study app that turns engineering PDFs into
> structured study material (notes, MCQs, flashcards, schedule).
>
> Primary constraint: **minimize cost; accept slowness freely.** Built for broke
> students. Items marked `<!-- inferred -->` are reconstructed — verify.

## Product summary

A local web app for university computer/electronic engineering students. Upload a
professor PDF or textbook → convert to markdown → detect structure → AI generates
per-topic study material within free-tier budgets → study via notes, quizzes,
flashcards on an SM-2 calendar. All data is local (SQLite). Cloud sync deferred.

## Locked decisions

1. **Input** — Professor PDF notes + textbook PDFs. (Manual paste deferred.)
2. **Ingestion** — `markitdown` → markdown first, cached by file hash, to cut
   tokens and avoid re-paying ingestion.
3. **Structure detection** — Automatic from headings, with a manual fallback.
4. **Granularity** — One chapter/topic per chunk. **The topic is the atomic unit
   of work and the DB transaction boundary** — never the whole document.
5. **Generation split** — Two AI calls per topic: notes (depth), then
   MCQs+flashcards together (consistency, notes as context).
6. **Formula handling** — Vision transcription of cropped equation regions → LaTeX
   (`[reconstructed]` → `[verified]`). Scoped to math-bearing regions to limit
   vision cost. Read, not guess.
7. **Cost is the primary constraint** — minimize spend; slowness (hours, overnight,
   across a Claude 5-hour window) is acceptable. See `cost-strategy.md`.
8. **Provider waterfall (cheapest-first, day one)** — Gemini free → other free →
   Ollama local (benchmark-gated) → paid Claude (last resort, hard-disable-able).
   Automatic failover on limit-hit, mid-job, without losing committed work.
9. **Never-zero-result guarantee** — process what fits the current budget, commit
   each topic immediately, queue the rest with a concrete resume time. A large PDF
   never returns nothing; it returns the most important topics first.
10. **Budget-aware dispatch** — each provider exposes a budget probe; the queue
    dispatches only what current headroom allows, then pauses with the rest queued.
11. **Persistent queue** — queue state lives in SQLite (`QueueJob`), surviving app
    restarts and limit windows; the student studies completed topics while waiting.
12. **Priority ordering** — `exam_critical` topics processed first; `skip` topics
    never sent to a model.
13. **No blocking** — Study View opens immediately after structure review.
14. **Editing** — Inline editing (TipTap) + manual note blocks; per-section
    regenerate with old-vs-new diff; regenerating notes flags assessments stale.
15. **Progress model** — Manual, per-topic, binary (studied = 100% or 0%).
16. **Scheduling** — Lightweight SM-2, plus a deadline mode that compresses
    intervals toward a subject's exam date.
17. **Budget probe is multi-axis** — returns the binding free-tier constraint
    (requests/min, requests/day, tokens), not a single number.
18. **Per-document cost estimate** — `est_cost_per_topic` seeded from this
    document's first topics, kept as a rolling estimate.
19. **Failover backoff** — walk the waterfall once; on full exhaustion, sleep
    until the earliest provider reset; exponential backoff on flaky providers;
    never spin.
20. **Ollama benchmarked on a laptop-class GTX 3060 (~6 GB VRAM)** baseline,
    including thermal/throttle behavior for sustained overnight runs; a model that
    needs a desktop GPU does not qualify as the default.
21. **Provider stamping** — each topic records the provider that generated it, so
    weak free-tier topics can be regenerated later on a better provider.
22. **Formula vision is exam-critical-first** — detect-then-crop on free tier;
    `medium` topics' formulas deferred; `skip` never transcribed; confidence-first
    review.
23. **Overnight mode (priority feature)** — free-only processing across as many
    reset windows as needed, notifying when all `exam_critical` topics are ready.
24. **Cost visibility** — live "spent / saved vs all-paid" readout and a
    pre-flight per-document estimate before processing.

## Resolved open questions

- **Default cost path** → Free API tiers first (Gemini free), paid Claude as
  fallback; **benchmark Gemini-free vs. Ollama** and pick the cost/performance
  winner as the bulk default rather than assuming.
- **On provider limit mid-job** → automatically switch to another free provider
  and keep going; pause only if no provider has headroom.
- **Flashcard repetition** → SM-2 (+ deadline mode), not a linear deck.
- **Study-session model** → topic-based, launched from the calendar, optional
  Pomodoro (top-bar timer).
- **Large PDF handling** → topic-atomic processing + persistent budget-aware queue;
  process in waves across free windows, commit-as-you-go.
- **Subjects/topics shape** → hierarchy (Subject → Chapter → Topic). <!-- inferred -->
- **Manual content depth** → full inline editing + separate manual blocks. <!-- inferred -->
- **Study-while-waiting** → guaranteed: any `ready` topic is fully studiable while
  the rest of the document is still queued or deferred to a reset window.

## Deferred

- Cloud sync (schema exports cleanly when added).
- Desktop packaging (Tauri/PyInstaller) — **dropped**; local web app.
- Cost-threshold *automatic* provider preference (order is user-configurable, but
  selection within the waterfall is cost-order + failover, not a learned threshold).
- Manual text/paste input.
