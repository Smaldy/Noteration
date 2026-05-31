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
    errors: list[QueueErrorTopic] = field(default_factory=list)


_STATUS_FIELDS = {
    TopicStatus.ready: "ready",
    TopicStatus.processing: "processing",
    TopicStatus.queued: "queued",
    TopicStatus.error: "error",
}


def get_queue_status(
    session: Session, *, document_id: int | None = None
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
    return status
