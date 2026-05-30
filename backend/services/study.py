"""Study service: transaction-owning entry points for review + calendar.

Composes the pure scheduler primitives (``backend.services.scheduler``) and owns
the request transaction (commit), mirroring the documents service. The scheduler
primitives stay clock-free and commit-free; this layer injects "today" (from the
router) and commits.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Chapter, Flashcard, ScheduleEntry, Subject, Topic
from backend.services import scheduler
from backend.services.scheduler import Grade


def get_due(db: Session, *, today: date, limit: int | None = None) -> list[Flashcard]:
    """The study queue: due reviews first, then new (never-scheduled) cards."""
    return scheduler.due_flashcards(db, today=today, limit=limit)


def _subject_of(db: Session, flashcard: Flashcard) -> Subject | None:
    return db.scalars(
        select(Subject)
        .join(Chapter, Chapter.subject_id == Subject.id)
        .join(Topic, Topic.chapter_id == Chapter.id)
        .where(Topic.id == flashcard.topic_id)
    ).first()


def review(db: Session, flashcard: Flashcard, grade: Grade, *, today: date) -> Flashcard:
    """Apply a self-grade to ``flashcard``, rebuild its subject's calendar, commit.

    Skip is inert: it changes no scheduling state, so it skips the calendar
    rebuild + commit entirely (rebuilding would needlessly churn every
    non-manual entry for the subject and reassign entry IDs for no change).
    """
    changed = scheduler.review_flashcard(db, flashcard, grade, today=today)
    if not changed:  # Skip
        return flashcard
    db.flush()  # make the card's new due_date visible to the calendar rebuild
    subject = _subject_of(db, flashcard)
    if subject is not None:
        scheduler.rebuild_schedule(db, subject, today=today)
    db.commit()
    db.refresh(flashcard)
    return flashcard


def get_calendar(db: Session, *, start: date, end: date) -> list[ScheduleEntry]:
    """All schedule entries with ``start <= date <= end`` (calendar view)."""
    return list(
        db.scalars(
            select(ScheduleEntry)
            .where(ScheduleEntry.date >= start, ScheduleEntry.date <= end)
            .order_by(ScheduleEntry.date, ScheduleEntry.topic_id)
        ).all()
    )
