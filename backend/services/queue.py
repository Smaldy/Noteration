"""Persistent, budget-aware processing queue (reliability core).

Sub-wave 4a: enqueue topics as per-stage ``QueueJob`` rows, order work
priority-first (``exam_critical`` before ``medium``; ``skip`` never enqueued),
respect per-topic stage dependencies (formula → notes → assessment), compute how
many jobs current provider headroom allows, and atomically claim the next
eligible job. Actual processing/failover/resume land in 4b–4c.

The topic is the atomic unit; nothing here ever spans the whole document.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.enums import QueueStage, QueueState, TopicPriority
from backend.models.hierarchy import Topic
from backend.models.processing import ProviderState, QueueJob
from backend.services.providers.base import (
    AllProvidersExhausted,
    ProviderResult,
)

# A stage processor runs the stage's model call(s) (via the waterfall) and
# writes its domain rows (Note/MCQ/Formula/...) to the session WITHOUT
# committing — the queue commits everything atomically so a stage is never
# half-written. It returns the ProviderResult for stamping + cost, or raises.
StageProcessor = Callable[[QueueJob, Session], ProviderResult]

# A job goes to `error` after this many failed attempts (then it poisons only
# itself; every other topic is unaffected).
MAX_ATTEMPTS = 3

# Stage execution order within a topic: formulas first (notes embed them), then
# notes, then assessment (which uses notes as context).
STAGE_ORDER: tuple[QueueStage, ...] = (
    QueueStage.formula,
    QueueStage.notes,
    QueueStage.assessment,
)
STAGE_RANK = {stage: i for i, stage in enumerate(STAGE_ORDER)}

# exam_critical dispatched first so partial completion yields what matters most.
PRIORITY_RANK = {TopicPriority.exam_critical: 0, TopicPriority.medium: 1}

# Default stages enqueued per topic. Formula may be a no-op when a topic has no
# math; it stays in the set so ordering/eligibility are uniform.
DEFAULT_STAGES: tuple[QueueStage, ...] = STAGE_ORDER


class QueueService:
    """Thin persistence-facing queue API over a SQLAlchemy session."""

    def __init__(self, session: Session, *, max_attempts: int = MAX_ATTEMPTS) -> None:
        self.session = session
        self.max_attempts = max_attempts

    def enqueue_topic(
        self, topic: Topic, stages: tuple[QueueStage, ...] = DEFAULT_STAGES
    ) -> list[QueueJob]:
        """Create pending jobs for a topic's stages (idempotent per stage).

        ``skip``-priority topics are never sent to a model, so none are created.
        """
        if topic.priority is TopicPriority.skip:
            return []

        # Query the DB for existing stages (not the cached relationship
        # collection, which can be stale within a session).
        existing = set(
            self.session.scalars(
                select(QueueJob.stage).where(QueueJob.topic_id == topic.id)
            ).all()
        )
        created: list[QueueJob] = []
        for stage in stages:
            if stage in existing:
                continue
            job = QueueJob(topic_id=topic.id, stage=stage)
            self.session.add(job)
            created.append(job)
        self.session.commit()
        return created

    def pending_in_priority_order(self) -> list[QueueJob]:
        """All pending jobs, ordered exam-critical-first then by position/stage."""
        jobs = self.session.scalars(
            select(QueueJob).where(QueueJob.state == QueueState.pending)
        ).all()
        return sorted(jobs, key=self._sort_key)

    def claim_next(self) -> QueueJob | None:
        """Atomically move the next eligible pending job to ``running``.

        Eligible = highest priority whose earlier-stage jobs for the same topic
        are all ``done``. Returns the claimed job, or None if nothing is ready.
        """
        for job in self.pending_in_priority_order():
            if self._prerequisites_done(job):
                job.state = QueueState.running
                self.session.commit()
                return job
        return None

    def process_job(self, job: QueueJob, processor: StageProcessor) -> QueueJob:
        """Run one claimed job's stage and commit the result atomically.

        Success: the processor's domain rows + the job's `done`/stamping + the
        provider's cost are committed together — a sub-stage commit that never
        leaves a topic half-written. Budget exhaustion defers the job back to
        `pending` with a `resume_after`; any other failure rolls back partial
        writes and retries, going to `error` after `max_attempts`.
        """
        try:
            result = processor(job, self.session)
        except AllProvidersExhausted as exc:
            # Not a job failure — a budget pause. Roll back any partial write,
            # requeue, and record when to resume. Attempts unchanged.
            self.session.rollback()
            job = self.session.get(QueueJob, job.id)
            job.state = QueueState.pending
            job.resume_after = exc.retry_at
            self.session.commit()
            return job
        except Exception as exc:  # noqa: BLE001 - a failed topic must poison only itself
            self.session.rollback()
            job = self.session.get(QueueJob, job.id)
            job.attempts += 1
            job.last_error = str(exc)
            job.state = (
                QueueState.failed
                if job.attempts >= self.max_attempts
                else QueueState.pending
            )
            self.session.commit()
            return job

        job.assigned_provider = result.provider
        job.last_error = None
        job.state = QueueState.done
        self._record_provider_usage(result)
        self.session.commit()
        return job

    @staticmethod
    def budget_count(headroom: int, est_cost_per_topic: int) -> int:
        """How many jobs current headroom allows: floor(headroom / est).

        A non-positive estimate means "unknown" → dispatch nothing (the caller
        seeds the per-document estimate from the first processed topics).
        """
        if est_cost_per_topic <= 0:
            return 0
        return max(0, headroom // est_cost_per_topic)

    # -- internals -----------------------------------------------------------

    def _sort_key(self, job: QueueJob) -> tuple[int, int, int, int]:
        topic = job.topic
        chapter = topic.chapter
        return (
            PRIORITY_RANK.get(topic.priority, 99),
            chapter.order_index,
            topic.order_index,
            STAGE_RANK[job.stage],
        )

    def _record_provider_usage(self, result: ProviderResult) -> None:
        """Accumulate spend/usage on the serving provider's ProviderState row."""
        state = self.session.scalars(
            select(ProviderState).where(ProviderState.provider == result.provider)
        ).one_or_none()
        if state is None:
            state = ProviderState(provider=result.provider)
            self.session.add(state)
        # Column defaults apply at flush, so a freshly-added row reads None here.
        state.total_cost = (state.total_cost or 0.0) + result.cost
        state.total_tokens = (
            (state.total_tokens or 0) + result.input_tokens + result.output_tokens
        )

    def _prerequisites_done(self, job: QueueJob) -> bool:
        rank = STAGE_RANK[job.stage]
        siblings = self.session.scalars(
            select(QueueJob).where(QueueJob.topic_id == job.topic_id)
        ).all()
        return all(
            sibling.state == QueueState.done
            for sibling in siblings
            if STAGE_RANK[sibling.stage] < rank
        )
