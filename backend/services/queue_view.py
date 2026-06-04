"""Read model for the Queue / Processing view (Phase 9e).

Aggregates topic-status counts (the never-zero-result surface: ready / processing
/ queued / error), the next provider-window wake-up, and the errored topics with
their last error for the retry UI. ``skip`` topics are excluded — they are never
sent to a model, so they are not "in the queue".
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Chapter, Subject, Topic
from backend.models.enums import QueueLaneState, QueueState, TopicPriority, TopicStatus
from backend.models.processing import QueueJob
from backend.services import history
from backend.services.providers.base import Provider
from backend.services.queue import QueueService, document_token_usage


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


# --- lane-aware status (Wave C) ---------------------------------------------


@dataclass
class LaneStatus:
    """One subject lane's live status for the queue screen."""

    subject_id: int
    subject_name: str
    # Reported state: running / paused / overnight / waiting (a blend of the
    # configured lane state and the runtime contention state).
    state: str
    queue_state: str  # configured lane state: running / paused / overnight
    ready: int = 0
    processing: int = 0
    queued: int = 0
    error: int = 0
    active_provider: str | None = None  # provider of this lane's running job
    waiting_for: str | None = None  # provider it's blocked on (when waiting)
    resume_at: datetime | None = None  # earliest deferred job in this lane


@dataclass
class ProviderLaneState:
    """A waterfall provider's coarse state for the global provider strip."""

    provider: str
    state: str  # active / cooling / disabled


@dataclass
class LaneQueueStatus:
    lanes: list[LaneStatus]
    active_provider: str | None  # the globally most-recent generating provider
    providers: list[ProviderLaneState]  # waterfall order + per-provider state


def _derive_lane_state(lane: LaneStatus) -> str:
    if lane.queue_state == QueueLaneState.paused.value:
        return "paused"
    if lane.waiting_for is not None and lane.active_provider is None:
        return "waiting"
    if lane.queue_state == QueueLaneState.overnight.value:
        return "overnight"
    return "running"


def _cooling_providers(session: Session) -> set[str]:
    """Provider names parsed from deferred jobs' recorded reasons ("<name>: ...").

    The waterfall cools providers in-memory, but it stamps the deferral reason on
    the job (e.g. "gemini_free: 429 …"), so a cooling provider is recoverable from
    the DB without persisting per-provider reset state.
    """
    reasons = session.scalars(
        select(QueueJob.last_error).where(
            QueueJob.state == QueueState.pending,
            QueueJob.resume_after.is_not(None),
            QueueJob.last_error.is_not(None),
        )
    ).all()
    names: set[str] = set()
    for reason in reasons:
        if reason and ":" in reason:
            names.add(reason.split(":", 1)[0].strip())
    return names


def get_lane_statuses(
    session: Session, providers: Sequence[Provider]
) -> LaneQueueStatus:
    """Per-subject lane status + the global provider strip (Wave C, point 11)."""
    queue = QueueService(session)
    waiting = queue.waiting_lanes(providers)

    lanes_by_id: dict[int, LaneStatus] = {
        sid: LaneStatus(
            subject_id=sid, subject_name=name, state="running", queue_state=str(qs)
        )
        for sid, name, qs in session.execute(
            select(Subject.id, Subject.name, Subject.queue_state)
        ).all()
    }

    present: set[int] = set()
    for sid, status, count in session.execute(
        select(Chapter.subject_id, Topic.status, func.count())
        .join(Topic, Topic.chapter_id == Chapter.id)
        .where(Topic.priority != TopicPriority.skip)
        .group_by(Chapter.subject_id, Topic.status)
    ).all():
        lane = lanes_by_id.get(sid)
        if lane is None:
            continue
        present.add(sid)
        setattr(lane, _STATUS_FIELDS[status], count)

    for sid, provider in session.execute(
        select(QueueJob.subject_id, QueueJob.assigned_provider).where(
            QueueJob.state == QueueState.running,
            QueueJob.assigned_provider.is_not(None),
        )
    ).all():
        lane = lanes_by_id.get(sid)
        if lane is not None and lane.active_provider is None:
            lane.active_provider = provider

    for sid, resume in session.execute(
        select(QueueJob.subject_id, func.min(QueueJob.resume_after))
        .where(
            QueueJob.state == QueueState.pending,
            QueueJob.resume_after.is_not(None),
        )
        .group_by(QueueJob.subject_id)
    ).all():
        lane = lanes_by_id.get(sid)
        if lane is not None:
            lane.resume_at = resume

    lanes: list[LaneStatus] = []
    for sid in present:
        lane = lanes_by_id[sid]
        lane.waiting_for = waiting.get(sid)
        lane.state = _derive_lane_state(lane)
        lanes.append(lane)
    lanes.sort(key=lambda lane: lane.subject_name.lower())

    active = history.last_generation_provider(session) or next(
        (lane.active_provider for lane in lanes if lane.active_provider), None
    )
    cooling = _cooling_providers(session)
    provider_states = [
        ProviderLaneState(
            provider=p.name,
            state="disabled"
            if not p.enabled
            else "cooling"
            if p.name in cooling
            else "active",
        )
        for p in providers
    ]
    return LaneQueueStatus(
        lanes=lanes, active_provider=active, providers=provider_states
    )


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
