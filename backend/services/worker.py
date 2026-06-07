"""Background generation worker — drives the persistent queue (reliability core).

The queue (``services/queue.py``) is pure and never sleeps; *something* has to
claim and process jobs. This worker is that something: a single background thread
that, on app startup, recovers orphaned jobs and then repeatedly drains the queue.
It rebuilds the provider waterfall from the persisted ``Settings`` each cycle, so a
newly-saved API key takes effect without a restart — which is exactly the gap that
left "I added my Gemini key and nothing happened".

Design choices that keep it honest:
- One worker thread, one job at a time (the queue is sequential by contract).
- Each tick uses its own short-lived session (no long-held identity map).
- When nothing is runnable it sleeps ``poll_interval`` — it never spins.
- With *no* provider configured it skips the drain entirely, so jobs stay
  ``pending`` (no exhaustion defer) and become claimable the instant a key lands.
- The queue already handles per-job failure/exhaustion atomically; anything that
  escapes a tick is logged and the thread carries on.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from backend.db.database import SessionLocal
from backend.models.hierarchy import utcnow
from backend.models.processing import QueueJob
from backend.models.settings import Settings
from backend.services import history
from backend.services.duplicator.search import drain_search_once
from backend.services.pipeline.formula import NO_OP_PROVIDER
from backend.services.pipeline.processors import make_pipeline_processor
from backend.services.providers.factory import build_waterfall_from_settings
from backend.services.providers.waterfall import Waterfall
from backend.services.queue import JobOutcome, QueueService
from backend.services.settings import get_settings

logger = logging.getLogger("backend.worker")

# Sleep between drains when there's nothing to do. Also bounds how stale config
# can be: a newly-confirmed document or a freshly-saved key is picked up within
# this window. Short, because polling a local SQLite file is negligible.
POLL_INTERVAL_SECONDS = 5.0
# Jobs per drain before the loop re-reads settings and yields. Bounds one tick's
# work so a long queue can't pin a single waterfall/config snapshot.
MAX_JOBS_PER_TICK = 50
# Duplicate-search jobs processed per tick. Small so the lower-priority Stage-2
# search lane never starves topic generation (which is drained first each cycle).
SEARCH_JOBS_PER_TICK = 3

# Mandatory gap between consecutive free-tier Gemini calls. 60s / 12s = 5 req/min,
# comfortably under Gemini's 15 RPM ceiling even with vision/retry jitter. All four
# offered Gemini models are free-tier, so the throttle applies whenever Gemini is
# the serving tier (single pinned model or rotation).
FREE_TIER_THROTTLE_SECONDS = 12.0


def _no_sleep(_seconds: float) -> None:
    """Default sleep for one-shot drains: do not block (only the worker throttles)."""


def _free_tier_throttle_seconds(settings: Settings) -> float:
    """Seconds to wait between model calls when Gemini's free tier is serving.

    Throttle when the Gemini tier is enabled and configured — every offered Gemini
    model (single or rotation) is free-tier, so its 60-second request window must
    not be breached in automated drains. (If a paid/local tier serves instead, the
    extra spacing is harmless.) Returns 0 when Gemini can't serve.
    """
    # ``gemini_enabled`` defaults True; a transient (un-flushed) Settings reads
    # None, so treat "not explicitly False" as enabled.
    if settings.gemini_enabled is False or not settings.api_key_gemini:
        return 0.0
    return FREE_TIER_THROTTLE_SECONDS


def _is_billable_call(outcome: JobOutcome, assigned_provider: str | None) -> bool:
    """True when a job actually consumed a provider request (not a formula no-op).

    Formula *registration* and failed/exhausted jobs spend no request quota, so the
    free-tier per-minute pacing must not count them.
    """
    return (
        outcome is JobOutcome.done
        and bool(assigned_provider)
        and assigned_provider != NO_OP_PROVIDER
    )


def _record_generation_history(
    session: Session, job: QueueJob, outcome: JobOutcome, seconds: float
) -> None:
    """Log a topic-generated history event (+ a provider switch when it changed).

    Only billable generations are logged — formula registration no-ops produce no
    studiable output and no provider switch. Best-effort: the audit log never
    breaks a drain.
    """
    if _is_billable_call(outcome, job.assigned_provider):
        history.record_generation_safe(
            session,
            topic_id=job.topic_id,
            subject_id=job.subject_id,
            provider=job.assigned_provider,
            seconds=seconds,
        )


def _settings_fingerprint(settings: Settings) -> tuple:
    """The provider-relevant slice of Settings that warrants a waterfall rebuild.

    The waterfall (and the per-provider rate limiters it owns) must be *reused*
    across drain ticks — otherwise the in-memory requests/min + requests/day
    history is wiped every cycle and the local throttle never holds, so we burst
    past the free-tier quota and the provider answers 429. We only rebuild when
    one of these inputs actually changes (e.g. the user saves a new key), which is
    also exactly when a rebuild is needed for the change to take effect.
    """
    order = settings.provider_order
    return (
        settings.api_key_gemini,
        settings.api_key_claude,
        settings.gemini_model,
        bool(settings.gemini_enabled),
        bool(settings.gemini_rotation),
        bool(settings.allow_paid),
        bool(settings.ollama_enabled),
        settings.ollama_model,
        tuple(order) if order else (),
    )


class WaterfallCache:
    """Reuses one ``Waterfall`` across ticks, rebuilding only on config change.

    Keeping the same instance preserves each provider's local budget history (the
    rolling rpm/rpd windows in ``providers/budget.py``) between drains, so the
    cheapest-first throttle actually limits sustained throughput instead of
    resetting to "full headroom" every poll interval.
    """

    def __init__(self) -> None:
        self._fingerprint: tuple | None = None
        self._waterfall: Waterfall | None = None

    def for_settings(
        self,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> Waterfall:
        fingerprint = _settings_fingerprint(settings)
        if self._waterfall is None or fingerprint != self._fingerprint:
            # Reference the module global so tests can monkeypatch the builder.
            self._waterfall = build_waterfall_from_settings(settings, clock=clock)
            self._fingerprint = fingerprint
        return self._waterfall


def _has_configured_provider(settings: Settings) -> bool:
    """True when at least one provider can actually serve a request.

    Gemini needs to be enabled *and* hold its free-tier key; Claude needs
    ``allow_paid`` *and* a key (the hard never-spend switch); Ollama needs to be
    enabled *and* have a model set (so a user can run/test a local model). With
    nothing usable we skip the drain so jobs stay ``pending`` rather than
    collecting a 5-minute exhaustion defer.
    """
    # ``gemini_enabled`` defaults True; a transient Settings reads None, so treat
    # "not explicitly False" as enabled.
    if settings.gemini_enabled is not False and settings.api_key_gemini:
        return True
    if settings.allow_paid and settings.api_key_claude:
        return True
    if settings.ollama_enabled and settings.ollama_model:
        return True
    return False


def drain_once(
    session: Session,
    *,
    max_jobs: int = MAX_JOBS_PER_TICK,
    clock: Callable[[], datetime] = utcnow,
    cache: WaterfallCache | None = None,
    sleep: Callable[[float], None] = _no_sleep,
) -> int:
    """Run one drain cycle on an open session; return jobs processed.

    No pending work, or no provider configured → no-op (0). Otherwise reuse (via
    ``cache``) the waterfall built from current ``Settings`` and drain it lane-aware:
    each cycle ``claim_dispatch`` claims ≤1 job per available provider (the
    per-provider cap + lane contention), and each claim is processed on a
    single-provider waterfall so it stays in its assigned slot. Sequential here (one
    job at a time) — the *running worker* runs the per-provider claims concurrently;
    this one-shot path is for tests and is directly unit-testable.

    ``sleep`` is invoked after each billable free-tier model call to enforce the
    per-minute pacing; it defaults to a no-op so one-shot callers/tests don't block.

    Passing a ``WaterfallCache`` keeps the provider rate-limit state alive between
    calls (the running worker does this); without one the waterfall is rebuilt each
    call, which is fine for one-shot callers and tests.
    """
    settings = get_settings(session)
    queue = QueueService(
        session,
        clock=clock,
        per_doc_token_budget=settings.per_document_token_budget,
    )
    if not queue.pending_in_priority_order():
        return 0
    if not _has_configured_provider(settings):
        return 0
    if cache is not None:
        waterfall = cache.for_settings(settings, clock=clock)
    else:
        waterfall = build_waterfall_from_settings(settings, clock=clock)
    providers_by_name = {p.name: p for p in waterfall.providers}
    throttle_seconds = _free_tier_throttle_seconds(settings)

    processed = 0
    while processed < max_jobs:
        claims = queue.claim_dispatch(waterfall.providers)
        if not claims:
            break
        for claim in claims:
            if processed >= max_jobs:
                break
            provider = providers_by_name.get(claim.provider)
            if provider is None:  # defensive: assigned provider vanished
                continue
            sub = Waterfall([provider], clock=clock)
            job = session.get(QueueJob, claim.job_id)
            started = clock()
            outcome = queue.process_job(job, make_pipeline_processor(sub))
            processed += 1
            _record_generation_history(
                session, job, outcome, (clock() - started).total_seconds()
            )
            if throttle_seconds > 0 and _is_billable_call(
                outcome, job.assigned_provider
            ):
                sleep(throttle_seconds)

    # Drain the independent Stage-2 duplicate-search lane with the remaining budget.
    remaining = max_jobs - processed
    if remaining > 0:

        def _search_throttle(job: QueueJob, outcome: JobOutcome) -> None:
            if throttle_seconds > 0 and _is_billable_call(outcome, job.assigned_provider):
                sleep(throttle_seconds)

        processed += drain_search_once(
            session, queue, waterfall, max_jobs=remaining, throttle=_search_throttle
        )
    return processed


class QueueWorker:
    """Owns the background thread that drains the queue for the running app."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] = SessionLocal,
        *,
        poll_interval: float = POLL_INTERVAL_SECONDS,
        max_jobs: int = MAX_JOBS_PER_TICK,
    ) -> None:
        self._session_factory = session_factory
        self._poll_interval = poll_interval
        self._max_jobs = max_jobs
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        # One cache for the worker's lifetime so provider rate-limit windows
        # persist across drains (rebuilt only when provider settings change).
        self._waterfall_cache = WaterfallCache()
        # Per-provider "earliest next dispatch" gate enforcing the free-tier
        # per-minute pacing while still letting *other* providers run concurrently
        # (a provider in its gate window is skipped by claim_dispatch, the rest
        # proceed). Mutated from per-claim worker threads, so guard it with a lock.
        self._provider_gate: dict[str, datetime] = {}
        self._gate_lock = threading.Lock()

    def start(self) -> None:
        """Recover orphaned jobs, then spawn the daemon drain thread (idempotent)."""
        if self._thread is not None:
            return
        self._recover_orphans()
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="noteration-queue-worker", daemon=True
        )
        self._thread.start()
        logger.info("Queue worker started (poll=%ss)", self._poll_interval)

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the loop and wait for the thread to wind down."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("Queue worker stopped")

    # -- internals -----------------------------------------------------------

    def _recover_orphans(self) -> None:
        session = self._session_factory()
        try:
            recovered = QueueService(session).recover_orphaned_jobs()
            if recovered:
                logger.info("Recovered %d orphaned job(s) to pending", recovered)
        except Exception:  # noqa: BLE001 - never let startup recovery kill boot
            logger.exception("Queue worker: orphan recovery failed")
        finally:
            session.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
                self._drain_search()
            except Exception:  # noqa: BLE001 - a bad tick must not kill the thread
                logger.exception("Queue worker tick failed; continuing")
            self._stop.wait(self._poll_interval)

    def _tick(self) -> None:
        """Drain the queue lane-aware until no slot is claimable.

        Each cycle plans one round of claims (≤1 per available provider) and runs
        them **concurrently** — one thread per provider slot — so distinct providers
        (e.g. Ollama + Gemini) genuinely process topics at the same time (point 7).
        Loops while work remains; the per-provider gate paces free-tier dispatch.
        The outer ``_run`` loop sleeps ``poll_interval`` once nothing is claimable.
        """
        while not self._stop.is_set():
            plan = self._plan_and_claim()
            if plan is None:
                return
            claims, waterfall, throttle_seconds = plan
            if len(claims) == 1:
                # Single slot — run inline; no thread overhead for the common case.
                self._process_claim(claims[0], waterfall, throttle_seconds)
            else:
                threads = [
                    threading.Thread(
                        target=self._process_claim,
                        args=(claim, waterfall, throttle_seconds),
                        name=f"noteration-dispatch-{claim.provider}",
                        daemon=True,
                    )
                    for claim in claims
                ]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()

    def _drain_search(self) -> None:
        """Drain a few Exercise-Duplicator search jobs (independent of generation).

        Sequential in its own short-lived session, after the generation dispatch for
        this cycle. Capped at ``SEARCH_JOBS_PER_TICK`` so it never starves topic
        generation; the free-tier pacing applies to its billable model calls too.
        """
        session = self._session_factory()
        try:
            # Idle fast-path: skip the settings load + waterfall build entirely when
            # the Stage-2 lane is empty (the common case on most ticks).
            if not QueueService(session).has_pending_search():
                return
            settings = get_settings(session)
            if not _has_configured_provider(settings):
                return
            queue = QueueService(
                session, per_doc_token_budget=settings.per_document_token_budget
            )
            waterfall = self._waterfall_cache.for_settings(settings)
            throttle_seconds = _free_tier_throttle_seconds(settings)

            def _throttle(job: QueueJob, outcome: JobOutcome) -> None:
                if throttle_seconds > 0 and _is_billable_call(
                    outcome, job.assigned_provider
                ):
                    time.sleep(throttle_seconds)

            drain_search_once(
                session,
                queue,
                waterfall,
                max_jobs=SEARCH_JOBS_PER_TICK,
                throttle=_throttle,
            )
        except Exception:  # noqa: BLE001 - a bad search drain must not kill the worker
            logger.exception("Queue worker: search drain failed; continuing")
        finally:
            session.close()

    def _plan_and_claim(self):
        """Plan + claim one dispatch cycle in a short-lived session.

        Returns ``(claims, waterfall, throttle_seconds)`` or ``None`` when nothing
        is claimable (no provider configured, no pending work, or every available
        provider is gated/in-flight).
        """
        session = self._session_factory()
        try:
            settings = get_settings(session)
            if not _has_configured_provider(settings):
                return None
            queue = QueueService(
                session, per_doc_token_budget=settings.per_document_token_budget
            )
            if not queue.pending_in_priority_order():
                return None
            waterfall = self._waterfall_cache.for_settings(settings)
            now = utcnow()
            with self._gate_lock:
                blocked = frozenset(
                    name for name, until in self._provider_gate.items() if until > now
                )
            claims = queue.claim_dispatch(waterfall.providers, blocked_providers=blocked)
            if not claims:
                return None
            logger.info("Queue worker dispatching %d claim(s)", len(claims))
            return claims, waterfall, _free_tier_throttle_seconds(settings)
        finally:
            session.close()

    def _process_claim(self, claim, waterfall: Waterfall, throttle_seconds: float) -> None:
        """Process one claimed job on its assigned single-provider waterfall."""
        session = self._session_factory()
        try:
            queue = QueueService(session)
            job = session.get(QueueJob, claim.job_id)
            if job is None:
                return
            provider = next(
                (p for p in waterfall.providers if p.name == claim.provider), None
            )
            if provider is None:
                self._release_claim(claim.job_id)
                return
            sub = Waterfall([provider], clock=utcnow)
            started = time.monotonic()
            outcome = queue.process_job(job, make_pipeline_processor(sub))
            _record_generation_history(
                session, job, outcome, time.monotonic() - started
            )
            if throttle_seconds > 0 and _is_billable_call(outcome, job.assigned_provider):
                with self._gate_lock:
                    self._provider_gate[claim.provider] = utcnow() + timedelta(
                        seconds=throttle_seconds
                    )
        except Exception:  # noqa: BLE001 - one bad claim must not kill the worker
            logger.exception("Queue worker: processing a claim failed")
            self._release_claim(claim.job_id)
        finally:
            session.close()

    def _release_claim(self, job_id: int) -> None:
        """Free a job stranded in ``running`` when a claim couldn't be processed."""
        session = self._session_factory()
        try:
            QueueService(session).release_running_job(job_id)
        except Exception:  # noqa: BLE001 - best-effort; never raise from cleanup
            logger.exception("Queue worker: releasing a stuck claim failed")
        finally:
            session.close()
