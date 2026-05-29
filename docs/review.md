# Project Review — Noteration

> Advisory. The planning docs are the source of truth. Every risk and suggestion
> previously raised has been **accepted and folded into the docs** — this file now
> records (a) what was resolved and where it lives, and (b) the few things still
> genuinely open or worth watching during the build.

## Resolved — folded into the docs

| Item | Decision | Lives in |
|---|---|---|
| Cost estimation accuracy | Seed `est_cost_per_topic` per-document from this doc's first topics; rolling estimate | cost-strategy.md |
| Multi-axis free quotas | Budget probe returns the **binding** constraint (rpm / rpd / tokens), not one number | cost-strategy.md, tech-stack.md |
| Ollama hidden cost (time/heat) | Benchmarked on the target baseline — **laptop-class GTX 3060 (~6 GB VRAM)**; thermal/throttle is a scored metric; overnight-to-local warned | cost-strategy.md, tech-stack.md |
| Quality variance across waterfall | Provider stamping per topic (`assigned_provider`); regenerate weak topics on a better provider | cost-strategy.md, ai-pipeline.md, data-model.md |
| Formula vision cost lever | detect-then-crop on free tier; escalate page only when math is present; **exam-critical topics' formulas first**, `medium` deferred | ai-pipeline.md (Stage 3), cost-strategy.md |
| Failover loops | Walk waterfall once; on full exhaustion schedule a single wake-up at earliest `reset_at`; exponential backoff on flaky providers — never spin | cost-strategy.md |
| API keys in plaintext | Acceptable for local single-user; kept out of logs/URLs; revisit if sync lands | (noted) tech-stack.md / data-model.md |
| Sub-stage commit clarity | Topic can show "notes ready · questions pending" instead of a misleading "ready" | ux-flows.md, data-model.md |
| Live money readout | "spent $X · saved vs all-paid ~$Y," backed by `ProviderState` | cost-strategy.md, ux-flows.md |
| Pre-flight estimate | "~N topics · ~H hours on free tier · ~$0 unless paid" before processing | cost-strategy.md, ux-flows.md |
| Exam-critical first (topics + vision) | Priority ordering for both dispatch and vision spend | cost-strategy.md, ai-pipeline.md |
| Overnight mode | **Priority feature**: free-only, across reset windows, notify when exam-critical done | cost-strategy.md, ux-flows.md (Queue) |
| Confidence-first formula review | Vision confidence stored; low-confidence surfaces first | ai-pipeline.md, data-model.md, ux-flows.md |
| Cache before re-processing | Ingestion checks `file_hash` cache first; never re-ingest | ai-pipeline.md, data-model.md |
| Trust banner aggressiveness | Dismisses **per-document**, not globally | ux-flows.md |
| Denormalized `Chapter.subject_id` | Keep consistent with parent on every write | data-model.md |

## Still open (decide during build, low risk)

1. **Ollama candidate model.** Which specific local model is the 3060-laptop
   default is left to the benchmark — intentionally not pre-committed. Tagged
   `<!-- inferred -->` in cost-strategy.md until measured.

2. **Equation detection method.** detect-then-crop is locked as the *strategy*, but
   the concrete detector (layout heuristic vs. a light vision pass to locate math)
   is unspecified. Pick the cheapest one that doesn't miss inline math; tagged in
   ai-pipeline.md Stage 3.

3. **SM-2 grade→quality mapping.** The Correct/Incorrect/Skip → SM-2 quality score
   mapping isn't pinned down. Standard SM-2 uses 0–5; a 3-button UI needs a chosen
   mapping (e.g. Skip=2, Incorrect=1, Correct=4/5 by latency). Tagged in
   ai-pipeline.md / data-model.md.

4. **Second free tier identity.** The waterfall reserves a slot for "other free
   tier" beyond Gemini; which provider/key fills it is unspecified.

## Watch during build (not blockers)

- **Per-minute walls on Gemini free** will be the most common real-world pause;
  make sure the queue surfaces "resuming ~HH:MM" clearly so it doesn't look stuck.
- **Sub-stage rollback** must be airtight: a topic interrupted between `notes` and
  `assessment` should never present as fully ready. Covered in design; verify in code.
- **Benchmark is config, not a one-off.** Re-run when models or free tiers change;
  store its output as data the waterfall reads.
