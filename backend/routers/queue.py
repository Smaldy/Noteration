"""Queue router — processing status, lane status/control, history, retry.

Thin: builds the waterfall from settings (a pure read — budget probes never spend
quota) and delegates to the queue view / service. See Waves 9e + B + C.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Subject, Topic
from backend.schemas.chapter import DocumentChaptersOut
from backend.schemas.queue import (
    ClearHistoryResult,
    HistoryEventOut,
    LaneQueueStatusOut,
    LaneStateUpdate,
    QueueStatusOut,
    RetryResult,
)
from backend.services import documents as docsvc
from backend.services import history, queue_view
from backend.services.providers.factory import build_waterfall_from_settings
from backend.services.queue import QueueService, SubjectLaneNotFound
from backend.services.settings import get_settings

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/status", response_model=QueueStatusOut)
def queue_status(
    document_id: int | None = None,
    session: Session = Depends(get_session),
) -> queue_view.QueueStatus:
    """Global topic-status counts, the next provider wake-up, and errored topics."""
    budget = get_settings(session).per_document_token_budget
    return queue_view.get_queue_status(
        session, document_id=document_id, per_doc_token_budget=budget
    )


@router.get("/chapters", response_model=list[DocumentChaptersOut])
def book_chapter_lanes(
    session: Session = Depends(get_session),
) -> list[docsvc.DocumentChapters]:
    """Chapter lanes for every in-progress book, grouped by document.

    Lets the Queue page always show per-chapter resume/pause controls, instead of
    only right after a structure confirm (which is the only place that set the old
    ``?document_id=`` param)."""
    return docsvc.get_book_chapter_groups(session)


@router.get("/lanes", response_model=LaneQueueStatusOut)
def lane_status(session: Session = Depends(get_session)) -> queue_view.LaneQueueStatus:
    """Per-subject lane status + the global provider strip (Wave C, point 11)."""
    waterfall = build_waterfall_from_settings(get_settings(session))
    return queue_view.get_lane_statuses(session, waterfall.providers)


@router.get("/history", response_model=list[HistoryEventOut])
def queue_history(
    subject_id: int | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
) -> list[history.HistoryEventView]:
    """Chronological generation history (topic generations + provider switches)."""
    limit = max(1, min(limit, 500))
    return history.recent_events_view(session, subject_id=subject_id, limit=limit)


@router.delete("/history", response_model=ClearHistoryResult)
def clear_history(
    scope: Literal["hour", "day", "all"] = "all",
    session: Session = Depends(get_session),
) -> ClearHistoryResult:
    """Clear the generation history — the last hour, the last day, or all of it."""
    deleted = history.clear_history(session, scope=scope)
    return ClearHistoryResult(scope=scope, deleted=deleted)


@router.post("/topics/{topic_id}/retry", response_model=RetryResult)
def retry_topic(
    topic_id: int,
    session: Session = Depends(get_session),
) -> RetryResult:
    """Requeue a topic's failed jobs so the queue picks them up again."""
    if session.get(Topic, topic_id) is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    retried = QueueService(session).retry_topic(topic_id)
    return RetryResult(topic_id=topic_id, retried_jobs=retried)


def _require_subject(session: Session, subject_id: int) -> None:
    if session.get(Subject, subject_id) is None:
        raise HTTPException(status_code=404, detail="Subject not found")


@router.post("/lanes/{subject_id}/pause", status_code=204)
def pause_lane(subject_id: int, session: Session = Depends(get_session)) -> None:
    """Pause a subject lane (Steam-style): stop new dispatch, hand off its provider."""
    _require_subject(session, subject_id)
    QueueService(session).pause_lane(subject_id)


@router.post("/lanes/{subject_id}/resume", status_code=204)
def resume_lane(subject_id: int, session: Session = Depends(get_session)) -> None:
    """Resume a paused lane from its highest-priority queued topic."""
    _require_subject(session, subject_id)
    QueueService(session).resume_lane(subject_id)


@router.post("/lanes/{subject_id}/overnight", status_code=204)
def set_overnight(
    subject_id: int,
    body: LaneStateUpdate,
    session: Session = Depends(get_session),
) -> None:
    """Toggle per-subject overnight mode (grind on free tiers across resets)."""
    _require_subject(session, subject_id)
    try:
        QueueService(session).set_overnight(subject_id, body.enabled)
    except SubjectLaneNotFound as exc:  # pragma: no cover - guarded above
        raise HTTPException(status_code=404, detail="Subject not found") from exc
