"""Notes router — edit notes, add manual blocks, delete (Study View editing)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Note
from backend.schemas.note import NoteCreate, NoteUpdate
from backend.schemas.topic import NoteOut
from backend.services import notes as notesvc

router = APIRouter(prefix="/notes", tags=["notes"])


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate,
    session: Session = Depends(get_session),
) -> Note:
    """Add a manual note block under a topic. 404 if the topic is unknown."""
    try:
        return notesvc.create_manual_note(session, payload.topic_id, payload.content_md)
    except notesvc.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found")


@router.patch("/{note_id}", response_model=NoteOut)
def update_note(
    note_id: int,
    payload: NoteUpdate,
    session: Session = Depends(get_session),
) -> Note:
    """Edit a note's markdown and/or lock state. 404 if the note is unknown."""
    try:
        return notesvc.update_note(
            session,
            note_id,
            content_md=payload.content_md,
            locked=payload.locked,
        )
    except notesvc.NoteNotFoundError:
        raise HTTPException(status_code=404, detail="Note not found")


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(
    note_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Delete a note block. 404 if the note is unknown."""
    try:
        notesvc.delete_note(session, note_id)
    except notesvc.NoteNotFoundError:
        raise HTTPException(status_code=404, detail="Note not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
