"""/study — flashcard review queue, self-grading, and the calendar."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Flashcard, ScheduleEntry
from backend.models.hierarchy import utcnow
from backend.schemas.study import CalendarEntryOut, FlashcardOut, ReviewRequest
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
) -> list[ScheduleEntry]:
    if end < start:
        raise HTTPException(status_code=422, detail="end must be on or after start")
    return study_service.get_calendar(db, start=start, end=end)
