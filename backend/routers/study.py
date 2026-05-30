"""/study — flashcard review queue, self-grading, and the calendar."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Flashcard
from backend.models.hierarchy import utcnow
from backend.schemas.study import (
    CalendarEntryOut,
    FlashcardOut,
    RescheduleRequest,
    ReviewRequest,
)
from backend.services import study as study_service

router = APIRouter(prefix="/study", tags=["study"])


def _today() -> date:
    """Server 'today' in UTC, matching the app's tz-aware UTC convention
    (utcnow / UTCDateTime) — not local-time ``date.today()`` which can be a day
    off near midnight in non-UTC timezones."""
    return utcnow().date()


@router.get("/due", response_model=list[FlashcardOut])
def get_due(
    limit: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_session),
) -> list[Flashcard]:
    return study_service.get_due(db, today=_today(), limit=limit)


@router.post("/flashcards/{flashcard_id}/review", response_model=FlashcardOut)
def review_flashcard(
    flashcard_id: int,
    payload: ReviewRequest,
    db: Session = Depends(get_session),
) -> Flashcard:
    flashcard = db.get(Flashcard, flashcard_id)
    if flashcard is None:
        raise HTTPException(status_code=404, detail="Flashcard not found")
    return study_service.review(db, flashcard, payload.grade, today=_today())


@router.get("/calendar", response_model=list[CalendarEntryOut])
def get_calendar(
    start: date,
    end: date,
    db: Session = Depends(get_session),
) -> list[CalendarEntryOut]:
    if end < start:
        raise HTTPException(status_code=422, detail="end must be on or after start")
    entries = study_service.get_calendar(db, start=start, end=end)
    return [
        CalendarEntryOut(
            id=entry.id,
            topic_id=entry.topic_id,
            topic_title=entry.topic.title,
            date=entry.date,
            is_revision_buffer=entry.is_revision_buffer,
            source=entry.source,
        )
        for entry in entries
    ]


@router.patch("/schedule/{entry_id}", response_model=CalendarEntryOut)
def reschedule(
    entry_id: int,
    payload: RescheduleRequest,
    db: Session = Depends(get_session),
) -> CalendarEntryOut:
    """Drag-drop reschedule: move an entry to a new date (becomes ``manual``)."""
    entry = study_service.reschedule_entry(db, entry_id, new_date=payload.date)
    if entry is None:
        raise HTTPException(status_code=404, detail="Schedule entry not found")
    return CalendarEntryOut(
        id=entry.id,
        topic_id=entry.topic_id,
        topic_title=entry.topic.title,
        date=entry.date,
        is_revision_buffer=entry.is_revision_buffer,
        source=entry.source,
    )
