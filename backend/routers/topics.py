"""Topics router — read a topic's generated content (Phase 9d)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Topic
from backend.schemas.bookmarks import BookmarkUpdate, TopicBookmarkOut
from backend.schemas.reorder import ReorderRequest
from backend.schemas.topic import GenerateMoreRequest, TopicContentOut
from backend.services import topics as topicsvc
from backend.services.pipeline.generation import (
    GenerationParseError,
    TopicSourceUnavailableError,
)
from backend.services.providers.base import AllProvidersExhausted

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


@router.post("/{topic_id}/formulas/transcribe", response_model=TopicContentOut)
def transcribe_topic_formulas(
    topic_id: int,
    session: Session = Depends(get_session),
) -> Topic:
    """Lazily transcribe a topic's pending formulas, then return its content.

    Called by the Study View when a topic is opened: flips ``pending`` formulas to
    ``reconstructed`` via the vision waterfall and returns the refreshed topic
    content (notes + formulas + assessment). 404 unknown topic; 503 when no
    provider has vision headroom right now.
    """
    try:
        topicsvc.transcribe_formulas(session, topic_id)
    except topicsvc.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found")
    except AllProvidersExhausted as exc:
        raise HTTPException(
            status_code=503,
            detail=exc.reason or "No vision provider available right now",
        )
    return topicsvc.get_topic_content(session, topic_id)


@router.post("/{topic_id}/generate", response_model=TopicContentOut)
def generate_more(
    topic_id: int,
    payload: GenerateMoreRequest,
    session: Session = Depends(get_session),
) -> Topic:
    """Generate more MCQs or flashcards for a topic on demand, then return it.

    Synchronous (like formula transcription) — one model call appends new items.
    404 unknown topic; 409 if the source markdown is missing; 502 if the model's
    output is unusable; 503 when no provider has headroom right now.
    """
    try:
        topicsvc.generate_more(session, topic_id, payload.kind)
    except topicsvc.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found")
    except TopicSourceUnavailableError:
        raise HTTPException(
            status_code=409, detail="Document source unavailable; re-ingest needed"
        )
    except AllProvidersExhausted as exc:
        raise HTTPException(
            status_code=503,
            detail=exc.reason or "No provider available right now",
        )
    except GenerationParseError:
        raise HTTPException(
            status_code=502,
            detail="The model returned unusable output. Please try again.",
        )
    return topicsvc.get_topic_content(session, topic_id)


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
