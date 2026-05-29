# AI Pipeline

> Updated to make **cost minimization the primary constraint** (see
> `cost-strategy.md`). The pipeline is now built around a budget-aware queue, a
> cheapest-first provider waterfall, and a never-zero-result guarantee: process
> what you can, commit it immediately, queue the rest. Slow is fine; zero is not.
>
> Items marked `<!-- inferred -->` are reconstructed from design logic.

## Overview

Five stages turn a PDF into study material. The expensive AI work (stages 3–4)
runs in a **budget-aware, priority-ordered background queue**, one topic at a
time as the atomic unit. The UI never blocks: the moment any topic is done, it's
studiable.

```
1. Ingestion   PDF → markdown (markitdown) + page image rendering   [cached]
2. Structure   detect chapters/topics → user reviews/edits tree
3. Formula     crop equation region → vision model → LaTeX          [scoped]
4. Generation  per topic: call 1 = notes, call 2 = MCQs + flashcards
5. Scheduler   SM-2 (+ deadline mode) → calendar
```

All model calls go through the **provider abstraction** (`generate`,
`transcribe_image`, plus a **budget probe**), so any provider in the waterfall —
Gemini free, a second free tier, Ollama local, or paid Claude — can serve any
stage. See `cost-strategy.md` for the waterfall and budget rules.

## The unit of work: one topic

Nothing dispatched to a model is ever larger than a single topic. There is no
code path that processes "the whole document" as one job. This is deliberate: it
is the structural fix for the failure where a model tries to deliver an entire
large job at once, hits a limit, and returns nothing.

- A topic's outputs are written to SQLite in **one transaction** on completion.
- A failed topic returns to `queued` (or `error` after N retries) and affects no
  other topic.
- Topics are dispatched in **priority order** (`exam_critical` first), so partial
  completion always yields the most important material first.

## Stage 1 — Ingestion (cached)

- `markitdown` converts the PDF to clean markdown, cutting input tokens before any
  model sees the text — the first and cheapest cost lever.
- Each page is rendered to an image (PyMuPDF) for later formula cropping.
- Both outputs are **cached to disk keyed by file hash**; re-processing never
  re-pays ingestion.
- Scanned/no-text PDFs are flagged here for the manual-structure fallback.

## Stage 2 — Structure detection

- Scan the markdown for heading patterns (`#`, `##`, "Chapter X", Roman numerals)
  to propose a chapter/topic tree.
- No headings → fallback: split by page range, define manually, or have a (cheap,
  free-tier) model propose a structure.
- The user reviews the tree: rename, merge, split, set per-topic priority
  (`exam_critical` / `medium` / `skip`), set the exam date. Confirming enqueues
  topics (skipping `skip` ones entirely) and opens the Study View immediately.

## Stage 3 — Formula transcription (vision, scoped)

Read formulas instead of repairing garbled text — the highest-leverage accuracy
change. Scoped to pages/regions that contain math so vision rates aren't paid
document-wide.

1. Identify pages/regions likely to contain equations. <!-- inferred: detection method is an open cost lever, see below -->
2. Crop the region from the rendered page image.
3. Send the crop to a vision-capable provider via `transcribe_image`.
4. Store the LaTeX as a Formula in state `reconstructed`, with a confidence flag.
5. In the Notes tab, `[reconstructed]` formulas are highlighted; clicking confirms
   them to `[verified]`. Low-confidence formulas surface first.

**Cost decision (locked):** detect-then-crop on the free tier, escalating a page
to full per-page transcription only when detection finds nothing but the page
clearly has math. To bound vision spend, **formula transcription runs for
`exam_critical` topics first**; `medium` topics' formulas are deferred to a
later/cheaper window, and `skip` topics are never transcribed.

## Stage 4 — Generation (2 calls per topic)

Two calls per topic, both through the provider layer, both with output token caps:

**Call 1 — Notes.** Dense, engineer-level notes. Gets its own call for depth.
Transcribed formulas are embedded.

**Call 2 — Assessment (MCQs + flashcards together).** Takes the notes as context
so questions stay consistent with the material; bundling the two keeps them
aligned with each other. 5–10 MCQs + 5–10 flashcards, flashcards initialized with
SM-2 defaults.

Bulk generation targets the **cheapest model that clears the quality benchmark**
(see `cost-strategy.md`). Two calls is the floor — we don't split further, to
avoid per-call overhead.

**Regeneration dependency:** regenerating notes marks the topic's assessment items
stale and offers to re-run Call 2; the UI shows an old-vs-new diff so a preferred
edit isn't silently lost.

## Stage 5 — Scheduler (SM-2 + deadline mode)

A lightweight SM-2 algorithm makes the calendar smart rather than a manual planner.

- Each flashcard carries `ease_factor` (default 2.5), `interval`, `repetitions`,
  `due_date`.
- Self-grading after a flip (Correct / Incorrect / Skip) updates these per SM-2.
  <!-- inferred: exact grade→quality mapping to confirm -->
- Due cards populate the calendar automatically; drag-drop reschedules; revision
  buffer days are visually distinct.
- **Deadline mode:** when a topic's subject has an exam date, intervals compress
  toward it and `exam_critical` topics are prioritized; standard SM-2 resumes when
  no exam date is set.

## Budget-aware queue & concurrency

The queue is where cost control lives. Full rules in `cost-strategy.md`; in brief:

- **Pre-flight budget probe.** Before dispatching, ask the active provider how
  much headroom it has (free-tier quota, or Claude's rolling 5-hour window). Only
  dispatch `floor(headroom / est_cost_per_topic)` topics; queue the rest with a
  concrete resume time.
- **Automatic failover.** On limit-hit or hard error, fail over to the next
  provider in the waterfall (free → free → local → paid) and keep going.
- **Concurrency** is low (2–3 topics) and further bounded by free-tier
  rate limits — throughput is whatever the free quota allows, and that's fine.
- **Status per topic:** `queued` / `processing` / `ready` / `error`, surfaced in
  the sidebar. The Library/queue view always shows "X ready now, Y queued,
  resuming ~HH:MM."
- **Provider stamping.** Each topic records which provider generated it
  (`QueueJob.assigned_provider`), surfaced in the UI so a weak free-tier topic can
  be regenerated later on a better provider.
- **Cache check first.** Before any (re)processing, ingestion checks the
  `file_hash`-keyed cache for existing markdown/page renders and reuses them — a
  topic is never re-ingested.
- A 400+ page document processes in waves across hours or multiple free windows;
  the student studies completed topics throughout.
