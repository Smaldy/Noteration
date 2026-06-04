"""Chapter router — per-chapter lane control (Chapter Lanes).

Thin: validates the chapter exists and delegates the pause/resume/overnight
transition to the queue service, which owns the in-flight rollback + lazy
enqueue semantics.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Chapter
from backend.schemas.chapter import ChapterQueueStateUpdate
from backend.services.queue import ChapterLaneNotFound, QueueService

router = APIRouter(prefix="/chapters", tags=["chapters"])


@router.patch("/{chapter_id}/queue_state", status_code=204)
def set_chapter_queue_state(
    chapter_id: int,
    body: ChapterQueueStateUpdate,
    session: Session = Depends(get_session),
) -> None:
    """Pause / resume / overnight a single chapter lane.

    ``paused`` stops its topics from being claimed (and rolls back any in-flight
    job); ``running`` / ``overnight`` enqueues jobs for any non-skip topic that
    has none yet, so resuming a chapter confirmed paused starts it processing.
    """
    if session.get(Chapter, chapter_id) is None:
        raise HTTPException(status_code=404, detail="Chapter not found")
    try:
        QueueService(session).set_chapter_state(chapter_id, body.queue_state)
    except ChapterLaneNotFound as exc:  # pragma: no cover - guarded above
        raise HTTPException(status_code=404, detail="Chapter not found") from exc
