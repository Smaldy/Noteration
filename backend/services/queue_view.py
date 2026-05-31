"""Read model for the Queue / Processing view (Phase 9e).

Aggregates topic-status counts (the never-zero-result surface: ready / processing
/ queued / error), the next provider-window wake-up, and the errored topics with
their last error for the retry UI. ``skip`` topics are excluded — they are never
sent to a model, so they are not "in the queue".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Chapter, Topic
from backend.models.enums import QueueState, TopicPriority, TopicStatus
from backend.models.processing import QueueJob
from backend.services.queue import document_token_usage


@dataclass
class QueueErrorTopic:
    topic_id: int
    title: str
    last_error: str | None


@dataclass
class QueueStatus:
    ready: int = 0
    processing: int = 0
    queued: int = 0
    error: int = 0
    total: int = 0
    resume_at: datetime | None = None
    # Why work is deferred until ``resume_at`` (the recorded provider error, e.g.
    # a 429 quota message), so a perpetually-throttled provider isn't invisible.
    paused_reason: str | None = None
    # Per-document token budget: a document is paused once it spends ≥ its ceiling
    # (cost guard). When scoped to a document these report that document; globally
    # ``budget_paused`` flags that *some* document is paused on budget.
    token_spent: int = 0
    token_budget: int = 0
    budget_paused: bool = False
    errors: list[QueueErrorTopic] = field(default_factory=list)


_STATUS_FIELDS = {
    TopicStatus.ready: "ready",
    TopicStatus.processing: "processing",
    TopicStatus.queued: "queued",
    TopicStatus.error: "error",
}


def get_queue_status(
    session: Session,
    *,
    document_id: int | None = None,
    per_doc_token_budget: int = 0,
) -> QueueStatus:
    """Counts + next wake-up + errored topics, optionally scoped to a document."""
    counts = select(Topic.status, func.count()).where(
        Topic.priority != TopicPriority.skip
    )
    errors_q = (
        select(Topic.id, Topic.title, QueueJob.last_error)
        .join(QueueJob, QueueJob.topic_id == Topic.id)
        .where(
            Topic.status == TopicStatus.error,
            QueueJob.state == QueueState.failed,
        )
    )
    if document_id is not None:
        counts = counts.join(Chapter, Topic.chapter_id == Chapter.id).where(
            Chapter.document_id == document_id
        )
        errors_q = errors_q.join(Chapter, Topic.chapter_id == Chapter.id).where(
            Chapter.document_id == document_id
        )

    status = QueueStatus()
    for topic_status, count in session.execute(
        counts.group_by(Topic.status)
    ).all():
        setattr(status, _STATUS_FIELDS[topic_status], count)
        status.total += count

    # One failed job per errored topic (first seen); dedupe by topic id.
    seen: set[int] = set()
    for topic_id, title, last_error in session.execute(errors_q).all():
        if topic_id in seen:
            continue
        seen.add(topic_id)
        status.errors.append(QueueErrorTopic(topic_id, title, last_error))

    # The earliest deferred job drives the wake-up; carry its recorded reason so
    # the UI can say *why* it is paused, not just when it resumes.
    deferred_q = (
        select(QueueJob.resume_after, QueueJob.last_error)
        .where(
            QueueJob.state == QueueState.pending,
            QueueJob.resume_after.is_not(None),
        )
        .order_by(QueueJob.resume_after.asc())
    )
    if document_id is not None:
        deferred_q = (
            deferred_q.join(Topic, QueueJob.topic_id == Topic.id)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(Chapter.document_id == document_id)
        )
    earliest = session.execute(deferred_q).first()
    if earliest is not None:
        status.resume_at, status.paused_reason = earliest

    _annotate_budget(session, status, document_id, per_doc_token_budget)
    return status


def _annotate_budget(
    session: Session,
    status: QueueStatus,
    document_id: int | None,
    per_doc_token_budget: int,
) -> None:
    """Fill in the per-document token-budget fields (cost guard surfacing)."""
    has_unfinished = (status.queued + status.processing) > 0
    if document_id is not None:
        spent, budget = document_token_usage(
            session, document_id, override_budget=per_doc_token_budget
        )
        status.token_spent = spent
        status.token_budget = budget
        status.budget_paused = budget > 0 and spent >= budget and has_unfinished
        return

    # Global view: flag (and report) the first document that is paused on budget.
    doc_ids = session.scalars(
        select(Chapter.document_id)
        .join(Topic, Topic.chapter_id == Chapter.id)
        .join(QueueJob, QueueJob.topic_id == Topic.id)
        .where(QueueJob.state == QueueState.pending)
        .distinct()
    ).all()
    for doc_id in doc_ids:
        spent, budget = document_token_usage(
            session, doc_id, override_budget=per_doc_token_budget
        )
        if budget > 0 and spent >= budget:
            status.token_spent = spent
            status.token_budget = budget
            status.budget_paused = True
            return
