# Cost Strategy

> The organizing constraint for Noteration. This app is built for broke students:
> **minimize cost first, accept slowness freely.** A large PDF taking hours — or
> resuming across a 5-hour Claude limit window — is fine. Returning nothing is not.
>
> This doc defines the cost model, the provider waterfall, the budget-aware queue,
> and the never-zero-result guarantee. The pipeline, queue, and provider docs
> implement what's specified here.

## Principles

1. **Free first, paid last.** Default to free API tiers. Paid Claude is a
   fallback, used only when free options are exhausted or quality demands it.
2. **Slow is acceptable; zero is not.** The user can wait hours or overnight. The
   only unacceptable outcome is a long job that fails and produces no studiable
   material.
3. **Commit early, commit often.** Every completed unit of work is persisted to
   SQLite immediately. Progress is never held in memory waiting for a "complete"
   job that might never arrive.
4. **The unit of work is one topic, never the whole document.** Nothing dispatched
   to a model is ever large enough that its failure loses meaningful work.
5. **Measure, don't guess.** The free-tier vs. local-model tradeoff is decided by
   a benchmark (see `## Benchmark: Gemini-free vs. Ollama`), not by assumption.

## Provider waterfall

Providers are tried in cost order. On a limit-hit or hard error, the queue fails
over to the next provider automatically and keeps going — without losing any
committed work.

```
1. Gemini free tier        (default, $0)
2. Other free tier(s)      (e.g. a second free key/model, $0)   <!-- inferred: which -->
3. Ollama local            (if installed; $0, slower)            <!-- benchmark-gated -->
4. Paid Claude             (last resort, costs money)
```

- The user can disable the paid tier entirely (a hard "never spend" switch in
  Settings) — in that case the waterfall stops at the last free option and the
  remaining work simply waits in the queue until a free window reopens.
- Order is configurable, but the default is strictly cheapest-first.

### Failover backoff (no spin loops)

Failover walks the waterfall **once** per dispatch attempt; it does not retry the
same providers in a tight loop. The rule:

1. Try providers in order. The first with headroom (per its budget probe) takes
   the topic.
2. If a provider hits a limit mid-call, mark it cooling (record its `reset_at`)
   and move to the next provider in the waterfall.
3. If **every** enabled provider is exhausted (and paid is disabled or also
   exhausted), the queue stops trying and **schedules a single wake-up at the
   earliest `reset_at`** across all providers. No further attempts happen until
   then.
4. On wake-up, re-probe and resume from the highest-priority queued topic.
5. Repeated immediate failures on the same provider apply exponential backoff
   (e.g. 1m → 2m → 4m, capped) before that provider is retried, so a flaky
   provider can't burn cycles.

This guarantees the queue is always either making progress or sleeping until a
known reset — never spinning.

## Budget-aware dispatch (pre-flight)

Before dispatching any topic, the queue asks the active provider: *how much can
you still do right now?* It only dispatches what fits, and queues the rest with a
concrete resume time. This is the mechanism that prevents the "tried to do
everything, did nothing" failure.

Each provider exposes a **budget probe** returning its current headroom. Free
tiers limit on several axes at once, so the probe returns the **binding
constraint** — the axis that will run out first — not a single number:

| Provider | Budget signals (probe returns the binding one) |
|---|---|
| Gemini free | requests-per-minute **and** requests-per-day **and** token quota |
| Claude paid | tokens remaining in the rolling 5-hour window; reset timestamp |
| Ollama local | always available (bounded only by local hardware throughput) |

> Modelling only one axis (e.g. daily quota) causes a classic failure: hitting the
> per-minute wall while believing there's plenty of daily headroom. The probe must
> evaluate every relevant axis and report whichever binds first, plus its reset time.

The queue maintains a running estimate of cost-per-topic and dispatches
`floor(headroom / est_cost_per_topic)` topics, then pauses with the rest queued.

**Estimate seeding (per-document, not global).** `est_cost_per_topic` is seeded
from the first few processed topics of *this* document — they are far more
representative of the document's density than a global average — and is kept as a
rolling per-document estimate thereafter. This avoids the two failure modes of a
bad estimate: under-using free quota (too conservative) or overshooting and
triggering needless failover (too optimistic).

## The 5-hour Claude window

When Claude is the active (fallback) provider and the rolling 5-hour usage window
is consumed mid-job:

1. The in-flight topic finishes if it can; if it can't, it is rolled back to
   `queued` (never left half-written — see never-zero-result guarantee).
2. The queue records the window reset timestamp.
3. The queue **fails over to a free provider** if one has headroom, and keeps
   processing.
4. If no provider has headroom, the queue pauses and shows: "X topics ready to
   study now, Y queued, resuming ~HH:MM." Already-processed topics remain fully
   studiable.

The student is never blocked from studying what's already done.

## Never-zero-result guarantee

This is the central reliability rule, enforced in the queue/orchestration layer:

- **Topic is the transaction boundary.** A topic's generated notes + assessment
  items are written to SQLite in one transaction the moment they complete.
- **A failed topic poisons only itself.** It returns to `queued` (or `error` after
  N retries); every other topic is unaffected.
- **No "finish the whole document" semantics anywhere.** There is no code path
  that waits for all topics before persisting any. Partial completion is the
  normal, expected state.
- **Ordering by priority.** `exam_critical` topics are dispatched first, so if only
  part of a document processes, it's the part that matters most.

> Why this matters: the prior failure mode was an LLM trying to deliver the entire
> 400-page job as one polished result, hitting a limit, and returning zero. Making
> the topic the atomic, immediately-committed unit removes that possibility
> structurally — the model is never asked to hold a large job open.

## Cost-reduction techniques for large PDFs

- **markitdown first** — strips visual noise, cuts input tokens substantially
  before any model sees the text.
- **Cache aggressively** — markitdown output and rendered page images are cached
  to disk keyed by file hash; re-processing a topic never re-pays ingestion.
- **Cheapest model that passes benchmark** — bulk note generation goes to the
  cheapest model that clears the quality bar (see benchmark). Only quality-
  sensitive steps escalate.
- **Vision calls only where needed, exam-critical first** — formula transcription
  (the one step that needs vision) is the cost wildcard: vision tokens dwarf text
  on free tiers. It is scoped to pages/regions that actually contain math, and on
  the free tier it is run **for `exam_critical` topics first**; `medium` topics'
  formulas are deferred to a later/cheaper window. (The detection-vs-per-page
  decision is specified in `ai-pipeline.md` Stage 3.)
- **Skip `skip`-priority topics** — topics the student marks `skip` in structure
  review are never sent to a model at all.
- **Batch within a topic** — the 2 calls per topic (notes; MCQs+flashcards) are
  the floor; we don't split further, to avoid per-call overhead.
- **Token budgets per call** — each call has a max output cap sized to the topic,
  so a runaway generation can't silently burn quota.

## Benchmark: Gemini-free vs. Ollama

We do not assume which is better; we measure. A small harness (see
`tech-stack.md` and `project-structure.md` for where it lives) runs the same set
of representative topics through:

- Gemini free tier
- Ollama local — benchmarked on the **target hardware baseline: a laptop-class
  GTX 3060 (≈6 GB VRAM)**. Candidate models must fit and run at acceptable speed on
  that tier; a model that only performs on a desktop GPU does not qualify as the
  default. <!-- model TBD by benchmark, constrained to 3060-laptop VRAM/throughput -->

and records, per topic:

| Metric | Why |
|---|---|
| $ cost | Gemini free = $0 but quota-limited; Ollama = $0 but slow |
| wall-clock time | students will wait, but not infinitely |
| note quality (rubric score) | dense, correct, exam-useful? |
| formula accuracy | the make-or-break for engineering material |
| throughput before limit | how many topics per free window / per hour |
| thermal/throttle behavior | sustained overnight runs on a 3060 laptop must not collapse |

The winner becomes the default bulk provider; the other stays in the waterfall.
Re-run the benchmark when models change.

## Cost visibility & processing modes

These are locked product behaviors, not just nice-to-haves.

- **Live money readout.** A persistent readout shows "spent: $X.XX · saved vs.
  all-paid: ~$Y" so the student can see the free-first mission working. Backed by
  `ProviderState.total_cost` / `total_tokens`.
- **Pre-flight estimate before processing.** On confirming a document the app
  shows "~N topics · ~H hours on free tier · ~$0 unless paid fallback is used,"
  derived from topic count and the per-document estimate seed. Sets expectations
  up front for large PDFs.
- **Overnight mode (priority feature).** A toggle: "process everything on free
  tiers, however long it takes, across as many reset windows as needed; notify me
  when all `exam_critical` topics are ready." This is the headline mode for the
  broke-student use case — it leans fully into "slow is fine, $0 is the goal" and
  pairs with priority ordering so the exam-critical material lands first.
- **Provider stamping.** Each topic records which provider generated it
  (`QueueJob.assigned_provider`), surfaced in the UI so the student can later
  regenerate a weak free-tier topic on a better provider. (See `ai-pipeline.md`.)
- **Confidence-first formula review.** Transcribed formulas carry a confidence
  score; low-confidence ones surface first in the `[reconstructed]` review queue,
  directing limited attention where errors are most likely.
