"""Persistent, budget-aware processing queue (reliability core).

Sub-wave 4a: enqueue topics as per-stage ``QueueJob`` rows, order work
priority-first (``exam_critical`` before ``medium``; ``skip`` never enqueued),
respect per-topic stage dependencies (formula → notes → assessment), compute how
many jobs current provider headroom allows, and atomically claim the next
eligible job. Actual processing/failover/resume land in 4b–4c.

The topic is the atomic unit; nothing here ever spans the whole document.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.enums import QueueStage, QueueState, TopicPriority
from backend.models.hierarchy import Topic
from backend.models.processing import QueueJob

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

    def __init__(self, session: Session) -> None:
        self.session = session

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
