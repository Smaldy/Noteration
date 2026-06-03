"""Study service: transaction-owning entry points for review + calendar.

Composes the pure scheduler primitives (``backend.services.scheduler``) and owns
the request transaction (commit), mirroring the documents service. The scheduler
primitives stay clock-free and commit-free; this layer injects "today" (from the
router) and commits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import Chapter, Document, Flashcard, ScheduleEntry, Subject, Topic
from backend.models.enums import ScheduleSource
from backend.services import scheduler
from backend.services.scheduler import Grade

# Sentinel for "field not provided" in a partial update (distinct from an
# explicit None/empty-string, which clears the field).
_UNSET = object()


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
    """All schedule entries with ``start <= date <= end`` (calendar view).

    Eager-loads the topic so the response can carry its title without an N+1.
    """
    return list(
        db.scalars(
            select(ScheduleEntry)
            .where(ScheduleEntry.date >= start, ScheduleEntry.date <= end)
            .options(
                selectinload(ScheduleEntry.topic).selectinload(Topic.chapter),
                selectinload(ScheduleEntry.subject),
            )
            .order_by(ScheduleEntry.date, ScheduleEntry.id)
        ).all()
    )


def reschedule_entry(
    db: Session, entry_id: int, *, new_date: date
) -> ScheduleEntry | None:
    """Move a calendar entry to a new date (drag-drop), marking it ``manual``.

    ``manual`` entries are preserved across scheduler rebuilds. Returns the
    updated entry, or None if the id is unknown.
    """
    return update_entry(db, entry_id, new_date=new_date)


class ScheduleEntryInvalidError(ValueError):
    """A calendar entry was created without a topic, subject, or title."""


def _resync_exam_date(db: Session, subject_id: int | None) -> None:
    """Set ``Subject.exam_date`` to the latest deadline marker for the subject.

    Keeps the planner / SM-2 deadline mode in step with the calendar: the exam
    date is the max date among the subject's ``is_deadline`` entries, or ``None``
    when there are none left. Called after a deadline marker is created, moved, or
    deleted. Does not commit (the caller's mutation commit covers it).
    """
    if subject_id is None:
        return
    subject = db.get(Subject, subject_id)
    if subject is None:
        return
    latest = db.scalars(
        select(ScheduleEntry.date)
        .where(
            ScheduleEntry.subject_id == subject_id,
            ScheduleEntry.is_deadline.is_(True),
        )
        .order_by(ScheduleEntry.date.desc())
    ).first()
    subject.exam_date = latest


def create_entry(
    db: Session,
    *,
    on_date: date,
    topic_id: int | None = None,
    subject_id: int | None = None,
    title: str | None = None,
    description: str | None = None,
    is_deadline: bool = False,
) -> ScheduleEntry:
    """Create a user-authored calendar entry (``source=manual``).

    Shapes (validated by the caller's schema): a topic session (``topic_id``), a
    whole-subject session (``subject_id``), a free-text custom event (``title``
    only), or a deadline/exam marker (``is_deadline`` + ``subject_id``). A deadline
    sets the subject's ``exam_date`` so the AI planner optimises toward it. Raises
    ``LookupError`` for a missing topic/subject, ``ScheduleEntryInvalidError`` if
    nothing identifying is given. Manual entries survive scheduler rebuilds.
    Commits.
    """
    cleaned_title = (title or "").strip() or None
    if is_deadline and subject_id is None:
        raise ScheduleEntryInvalidError("a deadline needs a subject")
    if topic_id is None and subject_id is None and cleaned_title is None:
        raise ScheduleEntryInvalidError(
            "a calendar entry needs a topic, a subject, or a title"
        )
    if topic_id is not None and db.get(Topic, topic_id) is None:
        raise LookupError(f"topic {topic_id} not found")
    if subject_id is not None and db.get(Subject, subject_id) is None:
        raise LookupError(f"subject {subject_id} not found")

    entry = ScheduleEntry(
        topic_id=topic_id,
        subject_id=subject_id,
        date=on_date,
        title=cleaned_title,
        description=(description or "").strip() or None,
        source=ScheduleSource.manual,
        is_deadline=is_deadline,
    )
    db.add(entry)
    if is_deadline:
        db.flush()
        _resync_exam_date(db, subject_id)
    db.commit()
    db.refresh(entry)
    return entry


def update_entry(
    db: Session,
    entry_id: int,
    *,
    new_date: date | None = None,
    title: object = _UNSET,
    description: object = _UNSET,
    completed: bool | None = None,
    today: date | None = None,
) -> ScheduleEntry | None:
    """Partially update a calendar entry. Returns it, or None if unknown.

    Moving the date marks the entry ``manual`` so the move survives an SM-2
    rebuild (matches the original drag-drop behavior). Toggling ``completed`` is
    independent of source — checking off an auto (sm2/deadline) review keeps it
    machine-managed, and the checkmark is carried forward by ``rebuild_schedule``.
    ``completed_at`` is stamped with ``today`` (the on-time/late reference is the
    entry's scheduled ``date``). Commits.
    """
    entry = db.get(ScheduleEntry, entry_id)
    if entry is None:
        return None
    date_changed = new_date is not None and new_date != entry.date
    if date_changed:
        entry.date = new_date
        # A deadline marker stays a deadline when moved; other entries become
        # ``manual`` so the move survives an SM-2 rebuild.
        if not entry.is_deadline:
            entry.source = ScheduleSource.manual
    if title is not _UNSET:
        entry.title = (title or "").strip() or None if isinstance(title, str) else None
    if description is not _UNSET:
        entry.description = (
            (description or "").strip() or None if isinstance(description, str) else None
        )
    if completed is not None:
        entry.completed = completed
        entry.completed_at = (today or date.today()) if completed else None
    # Moving a deadline marker re-syncs the subject's exam date.
    if entry.is_deadline and date_changed:
        db.flush()
        _resync_exam_date(db, entry.subject_id)
    db.commit()
    db.refresh(entry)
    return entry


def delete_entry(db: Session, entry_id: int) -> bool:
    """Delete a calendar entry. Returns True if it existed, False otherwise.

    Deleting a deadline marker re-syncs the subject's ``exam_date`` (to the next
    remaining deadline, or ``None``)."""
    entry = db.get(ScheduleEntry, entry_id)
    if entry is None:
        return False
    was_deadline = entry.is_deadline
    subject_id = entry.subject_id
    db.delete(entry)
    if was_deadline:
        db.flush()
        _resync_exam_date(db, subject_id)
    db.commit()
    return True


@dataclass
class CatalogTopic:
    id: int
    title: str
    chapter_title: str
    document_id: int
    studied: bool


@dataclass
class CatalogSubject:
    id: int
    name: str
    topics: list[CatalogTopic] = field(default_factory=list)


def topic_catalog(db: Session) -> list[CatalogSubject]:
    """All subjects with their topics, for the calendar's "study a topic" picker.

    One join (no N+1); grouped by subject in document/chapter/topic order so the
    picker reads top-down. Subjects with no topics are still listed (so the
    "whole subject" option is always available).
    """
    rows = db.execute(
        select(Subject, Topic, Chapter, Document)
        .join(Document, Document.subject_id == Subject.id, isouter=True)
        .join(Chapter, Chapter.document_id == Document.id, isouter=True)
        .join(Topic, Topic.chapter_id == Chapter.id, isouter=True)
        .order_by(
            Subject.name,
            Subject.id,
            Document.order_index,
            Document.id,
            Chapter.order_index,
            Chapter.id,
            Topic.order_index,
            Topic.id,
        )
    ).all()

    by_subject: dict[int, CatalogSubject] = {}
    for subject, topic, chapter, document in rows:
        cat = by_subject.get(subject.id)
        if cat is None:
            cat = CatalogSubject(id=subject.id, name=subject.name)
            by_subject[subject.id] = cat
        if topic is not None:
            cat.topics.append(
                CatalogTopic(
                    id=topic.id,
                    title=topic.title,
                    chapter_title=chapter.title,
                    document_id=document.id,
                    studied=topic.studied,
                )
            )
    return list(by_subject.values())
