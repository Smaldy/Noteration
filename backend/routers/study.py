"""/study — flashcard review queue, self-grading, and the calendar."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Flashcard, ScheduleEntry
from backend.models.hierarchy import utcnow
from backend.schemas.study import (
    CalendarEntryOut,
    CatalogSubjectOut,
    FlashcardOut,
    PlanRequest,
    ReviewRequest,
    ScheduleEntryCreate,
    ScheduleEntryUpdate,
)
from backend.services import planner as planner_service
from backend.services import study as study_service
from backend.services.providers.base import AllProvidersExhausted

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


def _entry_out(entry: ScheduleEntry) -> CalendarEntryOut:
    """Flatten a ScheduleEntry into the calendar response.

    ``kind`` and the display ``title`` are derived: a topic session deep-links
    into the Study View; a subject session carries the subject; a custom event
    is free text. ``on_time`` compares the completion to the scheduled date.
    """
    topic = entry.topic
    subject = entry.subject
    if entry.is_deadline:
        kind = "deadline"
    elif topic is not None:
        kind = "topic"
    elif entry.subject_id is not None:
        kind = "subject"
    else:
        kind = "custom"

    display = entry.title
    if not display:
        if entry.is_deadline:
            display = f"{subject.name} exam" if subject is not None else "Deadline"
        elif topic is not None:
            display = topic.title
        elif subject is not None:
            display = f"Study {subject.name}"
        else:
            display = "Study session"

    on_time: bool | None = None
    if entry.completed and entry.completed_at is not None:
        on_time = entry.completed_at <= entry.date

    return CalendarEntryOut(
        id=entry.id,
        date=entry.date,
        start_time=entry.start_time.strftime("%H:%M") if entry.start_time else None,
        source=entry.source,
        is_revision_buffer=entry.is_revision_buffer,
        is_deadline=entry.is_deadline,
        kind=kind,
        title=display,
        description=entry.description,
        completed=entry.completed,
        completed_at=entry.completed_at,
        on_time=on_time,
        topic_id=entry.topic_id,
        topic_title=topic.title if topic is not None else None,
        document_id=topic.chapter.document_id if topic is not None else None,
        subject_id=entry.subject_id,
        subject_name=subject.name if subject is not None else None,
    )


@router.get("/calendar", response_model=list[CalendarEntryOut])
def get_calendar(
    start: date,
    end: date,
    db: Session = Depends(get_session),
) -> list[CalendarEntryOut]:
    if end < start:
        raise HTTPException(status_code=422, detail="end must be on or after start")
    entries = study_service.get_calendar(db, start=start, end=end)
    return [_entry_out(entry) for entry in entries]


@router.get("/topic-catalog", response_model=list[CatalogSubjectOut])
def topic_catalog(db: Session = Depends(get_session)) -> list:
    """Subjects → topics, for the calendar's 'study a topic/subject' picker."""
    return study_service.topic_catalog(db)


@router.post("/schedule", response_model=CalendarEntryOut, status_code=201)
def create_schedule_entry(
    payload: ScheduleEntryCreate,
    db: Session = Depends(get_session),
) -> CalendarEntryOut:
    """Add a calendar entry: a topic session, a subject session, or a custom event."""
    try:
        entry = study_service.create_entry(
            db,
            on_date=payload.date,
            start_time=payload.start_time,
            topic_id=payload.topic_id,
            subject_id=payload.subject_id,
            title=payload.title,
            description=payload.description,
            is_deadline=payload.is_deadline,
        )
    except study_service.ScheduleEntryInvalidError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _entry_out(entry)


@router.patch("/schedule/{entry_id}", response_model=CalendarEntryOut)
def update_schedule_entry(
    entry_id: int,
    payload: ScheduleEntryUpdate,
    db: Session = Depends(get_session),
) -> CalendarEntryOut:
    """Edit a calendar entry: move it (becomes ``manual``), rename, re-note, or
    check it off as studied. Any subset of fields may be sent."""
    provided = payload.model_dump(exclude_unset=True)
    # Only forward title/description when the client actually sent them, so an
    # omitted field is left unchanged (vs. an explicit null/"" which clears it).
    field_kwargs: dict = {}
    if "start_time" in provided:
        field_kwargs["start_time"] = payload.start_time
    if "title" in provided:
        field_kwargs["title"] = payload.title
    if "description" in provided:
        field_kwargs["description"] = payload.description
    entry = study_service.update_entry(
        db,
        entry_id,
        new_date=payload.date,
        completed=payload.completed if "completed" in provided else None,
        today=_today(),
        **field_kwargs,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Schedule entry not found")
    return _entry_out(entry)


@router.delete("/schedule/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_entry(
    entry_id: int,
    db: Session = Depends(get_session),
) -> Response:
    """Remove a calendar entry (custom event or session)."""
    if not study_service.delete_entry(db, entry_id):
        raise HTTPException(status_code=404, detail="Schedule entry not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/plan", response_model=list[CalendarEntryOut], status_code=201)
def create_plan(
    payload: PlanRequest,
    db: Session = Depends(get_session),
) -> list[CalendarEntryOut]:
    """Generate an AI study plan for a subject (distributes its topics to dates).

    Replaces the subject's previous AI plan; manual events + the SM-2 calendar
    are untouched. 404 unknown subject; 409 no studyable topics; 502 unusable
    model output; 503 when no provider has headroom right now.
    """
    try:
        entries = planner_service.generate_study_plan(
            db,
            payload.subject_id,
            today=_today(),
            studied_topic_ids=payload.studied_topic_ids,
        )
    except planner_service.SubjectNotFoundError:
        raise HTTPException(status_code=404, detail="Subject not found")
    except planner_service.NoTopicsToPlanError:
        raise HTTPException(
            status_code=409,
            detail="No topics left to plan — every topic is marked studied or skipped.",
        )
    except AllProvidersExhausted as exc:
        raise HTTPException(
            status_code=503,
            detail=exc.reason or "No provider available right now",
        )
    except planner_service.PlanParseError:
        raise HTTPException(
            status_code=502,
            detail="The model returned an unusable plan. Please try again.",
        )
    return [_entry_out(entry) for entry in entries]


@router.delete("/plan/{subject_id}")
def delete_plan(
    subject_id: int,
    db: Session = Depends(get_session),
) -> dict[str, int]:
    """Delete a subject's AI plan (its ``ai`` entries). Manual + SM-2 untouched."""
    deleted = planner_service.delete_plan(db, subject_id)
    return {"deleted": deleted}
