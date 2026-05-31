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
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from backend.db.database import SessionLocal
from backend.models.hierarchy import utcnow
from backend.models.settings import Settings
from backend.services.pipeline.processors import make_pipeline_processor
from backend.services.providers.factory import build_waterfall_from_settings
from backend.services.queue import QueueService
from backend.services.settings import get_settings

logger = logging.getLogger("backend.worker")

# Sleep between drains when there's nothing to do. Also bounds how stale config
# can be: a newly-confirmed document or a freshly-saved key is picked up within
# this window. Short, because polling a local SQLite file is negligible.
POLL_INTERVAL_SECONDS = 5.0
# Jobs per drain before the loop re-reads settings and yields. Bounds one tick's
# work so a long queue can't pin a single waterfall/config snapshot.
MAX_JOBS_PER_TICK = 50


def _has_configured_provider(settings: Settings) -> bool:
    """True when at least one provider can actually serve a request.

    Gemini needs its free-tier key; Claude needs ``allow_paid`` *and* a key (the
    hard never-spend switch). Ollama is benchmark-gated (no model wired in the
    live waterfall yet), so it can't serve on its own here. With nothing usable we
    skip the drain so jobs stay ``pending`` rather than collecting a 5-minute
    exhaustion defer.
    """
    if settings.api_key_gemini:
        return True
    if settings.allow_paid and settings.api_key_claude:
        return True
    return False


def drain_once(
    session: Session,
    *,
    max_jobs: int = MAX_JOBS_PER_TICK,
    clock: Callable[[], datetime] = utcnow,
) -> int:
    """Run one drain cycle on an open session; return jobs processed.

    No pending work, or no provider configured → no-op (0). Otherwise build the
    waterfall from current ``Settings`` and hand a stage-dispatching processor to
    ``run_batch`` (which claims due jobs, respects defers, and stops on
    exhaustion). Pure of thread/sleep concerns so it's directly unit-testable.
    """
    queue = QueueService(session, clock=clock)
    if not queue.pending_in_priority_order():
        return 0
    settings = get_settings(session)
    if not _has_configured_provider(settings):
        return 0
    waterfall = build_waterfall_from_settings(settings, clock=clock)
    processor = make_pipeline_processor(waterfall)
    return queue.run_batch(processor, max_jobs=max_jobs)


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
            except Exception:  # noqa: BLE001 - a bad tick must not kill the thread
                logger.exception("Queue worker tick failed; continuing")
            self._stop.wait(self._poll_interval)

    def _tick(self) -> None:
        session = self._session_factory()
        try:
            processed = drain_once(session, max_jobs=self._max_jobs)
            if processed:
                logger.info("Queue worker processed %d job(s)", processed)
        finally:
            session.close()
