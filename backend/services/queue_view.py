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
from backend.services.queue import QueueService


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

    status.resume_at = QueueService(session).earliest_resume_after()
    return status
