"""Queue router — processing status + per-topic retry (Phase 9e)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Topic
from backend.schemas.queue import QueueStatusOut, RetryResult
from backend.services import queue_view
from backend.services.queue import QueueService
from backend.services.settings import get_settings

router = APIRouter(prefix="/queue", tags=["queue"])


@router.get("/status", response_model=QueueStatusOut)
def queue_status(
    document_id: int | None = None,
    session: Session = Depends(get_session),
) -> queue_view.QueueStatus:
    """Topic-status counts, the next provider wake-up, and errored topics."""
    budget = get_settings(session).per_document_token_budget
    return queue_view.get_queue_status(
        session, document_id=document_id, per_doc_token_budget=budget
    )


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
