"""SM-2 spaced-repetition scheduling (Phase 8).

The pure SM-2 core lives here (Phase 8a): it maps the three-button self-grade
(Correct / Incorrect / Skip) to an SM-2 quality score and advances a card's
scheduling state. DB-facing helpers (applying a grade to a ``Flashcard``,
materialising the ``ScheduleEntry`` calendar, deadline mode) build on this core
in later sub-waves of this module.

Per ``docs/ai-pipeline.md`` Stage 4:

  - Correct   → SM-2 success (quality ≥ 3): advance repetitions, grow interval,
                nudge ease up.
  - Incorrect → SM-2 lapse (quality < 3): reset repetitions, interval back to
                1 day, nudge ease down (floored at 1.3).
  - Skip      → no SM-2 change; the card reappears later in the session (triage).

Grade→quality mapping (resolves ``docs/review.md`` "Still open" #3): a 3-button
UI carries no latency signal, so we fix Correct = 5, Incorrect = 2, and treat
Skip as inert (no update at all). The core is pure — no clock, no DB — mirroring
the provider/queue seam; callers inject "today" and own persistence.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models import Chapter, Flashcard, ScheduleEntry, Subject, Topic
from backend.models.enums import ScheduleSource

DEFAULT_EASE_FACTOR = 2.5
MIN_EASE_FACTOR = 1.3

# Trailing days (including the exam day) flagged as revision buffer in deadline
# mode — the cram window where scheduled reviews are visually distinct.
REVISION_BUFFER_DAYS = 2


class Grade(enum.StrEnum):
    """The three-button self-grade. Transient review input; never persisted."""

    correct = "correct"
    incorrect = "incorrect"
    skip = "skip"


# Self-grade → SM-2 quality (0-5). Skip is intentionally absent: it performs no
# SM-2 update at all (see ``quality_for`` / ``apply_grade``).
_GRADE_QUALITY: dict[Grade, int] = {
    Grade.correct: 5,
    Grade.incorrect: 2,
}


@dataclass(frozen=True)
class CardState:
    """The SM-2 state of a single flashcard (mirrors the ``Flashcard`` fields)."""

    ease_factor: float = DEFAULT_EASE_FACTOR
    interval: int = 0
    repetitions: int = 0


def quality_for(grade: Grade) -> int | None:
    """Return the SM-2 quality (0-5) for a self-grade, or ``None`` for Skip."""
    return _GRADE_QUALITY.get(grade)


def sm2_update(state: CardState, quality: int) -> CardState:
    """Advance ``state`` by one SM-2 review at ``quality`` (0-5).

    ``quality < 3`` is a lapse: repetitions reset to 0 and the interval drops
    back to 1 day. ``quality >= 3`` advances the interval (1 → 6 → round(I·EF)).
    The ease factor is always nudged by the SM-2 response-quality formula and
    floored at ``MIN_EASE_FACTOR``.
    """
    if not 0 <= quality <= 5:
        raise ValueError(f"SM-2 quality must be 0..5, got {quality!r}")

    if quality < 3:
        repetitions = 0
        interval = 1
    elif state.repetitions == 0:
        repetitions, interval = 1, 1
    elif state.repetitions == 1:
        repetitions, interval = 2, 6
    else:
        repetitions = state.repetitions + 1
        # Interval uses the *current* ease factor, before this review's nudge.
        interval = round(state.interval * state.ease_factor)

    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    ease_factor = max(MIN_EASE_FACTOR, state.ease_factor + delta)
    return CardState(
        ease_factor=ease_factor, interval=interval, repetitions=repetitions
    )


def apply_grade(state: CardState, grade: Grade) -> CardState | None:
    """Advance ``state`` for a self-grade.

    Returns the new state, or ``None`` for Skip (no SM-2 change — the caller
    re-shows the card later in the session without touching scheduling state).
    """
    quality = quality_for(grade)
    if quality is None:
        return None
    return sm2_update(state, quality)


# --------------------------------------------------------------------------- #
# DB layer (Phase 8b): apply a self-grade to a Flashcard row and set its next
# review date. The pure SM-2 core above does the arithmetic; this owns the row
# mutation but not the transaction (the caller commits, mirroring the
# queue/generation seam). "today" is injected so the layer stays clock-free.
#
# Deadline mode is driven by the subject's exam date (ai-pipeline.md Stage 5):
# there is no settings flag. When the card's subject has an exam date still in
# the future, intervals are compressed so no review is scheduled past it.
# --------------------------------------------------------------------------- #


def subject_exam_date(session: Session, flashcard: Flashcard) -> date | None:
    """The exam date of the subject this flashcard belongs to (or None)."""
    return session.execute(
        select(Subject.exam_date)
        .join(Chapter, Chapter.subject_id == Subject.id)
        .join(Topic, Topic.chapter_id == Chapter.id)
        .where(Topic.id == flashcard.topic_id)
    ).scalar_one_or_none()


def review_flashcard(
    session: Session,
    flashcard: Flashcard,
    grade: Grade,
    *,
    today: date,
) -> None:
    """Apply a self-grade to ``flashcard`` and schedule its next review.

    Correct/Incorrect advance the card's SM-2 state and set ``due_date`` to
    ``today + interval`` (a calendar date). In deadline mode (the subject has a
    future exam date) the interval is compressed so the next review never lands
    past the exam. Skip is inert — it returns without touching the card, so the
    caller can re-show it later in the session. Does not commit.
    """
    new_state = apply_grade(
        CardState(flashcard.ease_factor, flashcard.interval, flashcard.repetitions),
        grade,
    )
    if new_state is None:  # Skip
        return

    interval = new_state.interval
    exam_date = subject_exam_date(session, flashcard)
    if exam_date is not None and exam_date > today:
        interval = min(interval, (exam_date - today).days)

    flashcard.ease_factor = new_state.ease_factor
    flashcard.repetitions = new_state.repetitions
    flashcard.interval = interval
    flashcard.due_date = today + timedelta(days=interval)


# --------------------------------------------------------------------------- #
# Calendar + study queue (Phase 8c). The calendar (``ScheduleEntry``) is a
# projection of the flashcards' due dates onto topics/dates, rebuilt after each
# review. ``due_flashcards`` is the study-session read side. Both are clock-free
# (today injected); callers commit.
# --------------------------------------------------------------------------- #


def _subject_topic_ids(session: Session, subject: Subject) -> list[int]:
    """Topic ids belonging to ``subject`` (via its chapters)."""
    return list(
        session.scalars(
            select(Topic.id)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(Chapter.subject_id == subject.id)
        ).all()
    )


def rebuild_schedule(
    session: Session, subject: Subject, *, today: date
) -> list[ScheduleEntry]:
    """Rebuild ``subject``'s machine-generated calendar from flashcard due dates.

    One ``ScheduleEntry`` per (topic, date) a card is due — deduped across cards.
    ``source`` is ``deadline`` when the subject has a current exam date, else
    ``sm2``; in deadline mode the trailing ``REVISION_BUFFER_DAYS`` (through the
    exam day) are flagged ``is_revision_buffer``. User-placed ``manual`` entries
    (drag-drop reschedules) are preserved. Does not commit.
    """
    topic_ids = _subject_topic_ids(session, subject)
    if not topic_ids:
        return []

    # Replace only machine-generated entries; manual drag-drops survive.
    session.execute(
        delete(ScheduleEntry).where(
            ScheduleEntry.topic_id.in_(topic_ids),
            ScheduleEntry.source != ScheduleSource.manual,
        ),
        execution_options={"synchronize_session": False},
    )

    exam_date = subject.exam_date
    deadline = exam_date is not None and exam_date >= today
    source = ScheduleSource.deadline if deadline else ScheduleSource.sm2
    buffer_start = (
        exam_date - timedelta(days=REVISION_BUFFER_DAYS - 1) if deadline else None
    )

    entries: list[ScheduleEntry] = []
    for topic_id in topic_ids:
        due_dates = session.scalars(
            select(Flashcard.due_date)
            .where(Flashcard.topic_id == topic_id, Flashcard.due_date.is_not(None))
            .distinct()
        ).all()
        for due in sorted(set(due_dates)):
            is_buffer = bool(deadline and buffer_start <= due <= exam_date)
            entry = ScheduleEntry(
                topic_id=topic_id,
                date=due,
                source=source,
                is_revision_buffer=is_buffer,
            )
            session.add(entry)
            entries.append(entry)
    return entries


def due_flashcards(
    session: Session, *, today: date, limit: int | None = None
) -> list[Flashcard]:
    """Cards to study now: due reviews (``due_date <= today``) first, then new
    (never-scheduled, ``due_date is None``) cards. ``limit`` caps the result."""
    stmt = (
        select(Flashcard)
        .where((Flashcard.due_date <= today) | (Flashcard.due_date.is_(None)))
        # Dated reviews first (by date), then new cards; stable by id.
        .order_by(Flashcard.due_date.is_(None), Flashcard.due_date, Flashcard.id)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt).all())
