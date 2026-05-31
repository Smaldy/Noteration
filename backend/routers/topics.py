"""Topics router — read a topic's generated content (Phase 9d)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Topic
from backend.schemas.bookmarks import BookmarkUpdate, TopicBookmarkOut
from backend.schemas.reorder import ReorderRequest
from backend.schemas.topic import TopicContentOut
from backend.services import topics as topicsvc

router = APIRouter(prefix="/topics", tags=["topics"])


@router.put("/reorder", status_code=204)
def reorder_topics(
    payload: ReorderRequest,
    session: Session = Depends(get_session),
) -> Response:
    """Persist a chapter's manual topic order (drag-and-drop in the sidebar)."""
    topicsvc.reorder_topics(session, payload.ids)
    return Response(status_code=204)


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


@router.put("/{topic_id}/bookmark", response_model=TopicBookmarkOut)
def set_topic_bookmark(
    topic_id: int,
    payload: BookmarkUpdate,
    session: Session = Depends(get_session),
) -> Topic:
    """Bookmark or unbookmark a topic."""
    try:
        return topicsvc.set_bookmark(session, topic_id, bookmarked=payload.bookmarked)
    except topicsvc.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found")


@router.delete("/{topic_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_topic(
    topic_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Delete a topic and all its generated content (cascades)."""
    try:
        topicsvc.delete_topic(session, topic_id)
    except topicsvc.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
