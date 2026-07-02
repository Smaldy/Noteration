"""Topics router — read a topic's generated content (Phase 9d)."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Topic
from backend.schemas.bookmarks import BookmarkUpdate, TopicBookmarkOut
from backend.schemas.reorder import ReorderRequest
from backend.schemas.topic import (
    AttachmentOut,
    GenerateMoreRequest,
    MergeTopicsRequest,
    RegenerateNotesRequest,
    TopicContentOut,
)
from backend.services import attachments as attachsvc
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


@router.post("/{topic_id}/notes/regenerate", response_model=TopicContentOut)
def regenerate_notes(
    topic_id: int,
    payload: RegenerateNotesRequest,
    session: Session = Depends(get_session),
) -> Topic:
    """Regenerate a topic's AI notes on demand, then return its refreshed content.

    Synchronous (like generate-more) — one model call rewrites only the notes,
    leaving the quiz and flashcards (and SM-2 state) intact. 404 unknown topic;
    409 if the document is exam-only, the note is locked, or the source markdown is
    missing; 502 if the model's output is unusable; 503 when no provider has
    headroom right now.
    """
    try:
        topicsvc.regenerate_notes(session, topic_id, instructions=payload.instructions)
    except topicsvc.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found")
    except topicsvc.NotesNotSupportedError:
        raise HTTPException(
            status_code=409, detail="Exam-prep documents have no notes to regenerate"
        )
    except topicsvc.NoteLockedError:
        raise HTTPException(
            status_code=409, detail="This note is locked; unlock it to regenerate"
        )
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


@router.post("/{topic_id}/merge", status_code=status.HTTP_204_NO_CONTENT)
def merge_topics(
    topic_id: int,
    payload: MergeTopicsRequest,
    session: Session = Depends(get_session),
) -> Response:
    """Merge other topics into this one (semantics in ``topics.merge_topics``).

    204 on success — the client refetches whatever views it shows. 404 unknown
    topic; 400 when no valid source is given (e.g. only the target itself).
    """
    try:
        topicsvc.merge_topics(
            session,
            topic_id,
            payload.source_topic_ids,
            consolidate=payload.consolidate,
        )
    except topicsvc.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found")
    except topicsvc.InvalidMergeError:
        raise HTTPException(
            status_code=400, detail="Select at least one other topic to merge"
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{topic_id}/attachments", response_model=AttachmentOut, status_code=201
)
async def add_attachment(
    topic_id: int,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> attachsvc.NoteAttachment:
    """Attach a user-provided image or audio file to a topic's notes."""
    data = await file.read()
    try:
        attachment = attachsvc.add_attachment(
            session,
            topic_id,
            filename=file.filename or "attachment",
            content_type=file.content_type or "application/octet-stream",
            data=data,
        )
    except attachsvc.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found")
    except attachsvc.UnsupportedAttachmentError:
        raise HTTPException(
            status_code=400, detail="Only images and audio (up to 25 MB) are accepted"
        )
    attachment.url = attachsvc.attachment_url(attachment)
    return attachment


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
