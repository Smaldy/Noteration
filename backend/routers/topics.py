"""Topics router — read a topic's generated content (Phase 9d)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Topic
from backend.schemas.topic import TopicContentOut
from backend.services import topics as topicsvc

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("/{topic_id}", response_model=TopicContentOut)
def topic_content(
    topic_id: int,
    session: Session = Depends(get_session),
) -> Topic:
    """A topic's notes (+formulas), MCQs, and flashcards for the study tabs."""
    try:
        return topicsvc.get_topic_content(session, topic_id)
    except topicsvc.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found")
