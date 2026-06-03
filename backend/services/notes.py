"""Note service — edit notes, add manual blocks, delete.

The background queue *writes* AI notes (Phase 7). This service is the user-driven
counterpart: it lets the Study View edit a note's markdown in place, lock it,
append manual note blocks, and remove blocks. Notes stay stored as markdown
(``Note.content_md``) — the editor round-trips through it.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import Note, Topic


class NoteNotFoundError(LookupError):
    """Referenced note does not exist."""


class TopicNotFoundError(LookupError):
    """Referenced topic does not exist."""


def _load(session: Session, note_id: int) -> Note:
    """Fetch a note with its formulas eagerly loaded (for serialization)."""
    note = session.execute(
        select(Note)
        .where(Note.id == note_id)
        .options(selectinload(Note.formulas))
    ).scalar_one_or_none()
    if note is None:
        raise NoteNotFoundError(note_id)
    return note


def update_note(
    session: Session,
    note_id: int,
    *,
    content_md: str | None = None,
    locked: bool | None = None,
) -> Note:
    """Apply a partial edit to a note and return it (with formulas).

    Only fields passed as non-``None`` change. Editing an AI note's text does not
    flip ``is_manual`` — it is still that AI note, now user-corrected. Raises
    ``NoteNotFoundError`` if the note is missing.
    """
    note = _load(session, note_id)
    if content_md is not None:
        note.content_md = content_md
    if locked is not None:
        note.locked = locked
    session.commit()
    return _load(session, note_id)


def create_manual_note(session: Session, topic_id: int, content_md: str = "") -> Note:
    """Add a manual note block under a topic (below the AI note).

    Raises ``TopicNotFoundError`` if the topic does not exist.
    """
    topic = session.get(Topic, topic_id)
    if topic is None:
        raise TopicNotFoundError(topic_id)
    note = Note(topic_id=topic_id, content_md=content_md, is_manual=True)
    session.add(note)
    session.commit()
    return _load(session, note.id)


def delete_note(session: Session, note_id: int) -> None:
    """Delete a note (and its formulas, via cascade). Raises if missing."""
    note = session.get(Note, note_id)
    if note is None:
        raise NoteNotFoundError(note_id)
    session.delete(note)
    session.commit()
