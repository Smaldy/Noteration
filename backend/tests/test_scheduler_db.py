"""Phase 8b — scheduler DB layer: grade application + deadline compression."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from backend.models import Chapter, Document, Flashcard, Subject, Topic
from backend.services.scheduler import Grade, review_flashcard

TODAY = date(2026, 1, 1)


def _make_card(session, *, exam_date=None, ease=2.5, interval=0, reps=0, due_date=None):
    subj = Subject(name="Math", exam_date=exam_date)
    session.add(subj)
    session.flush()
    doc = Document(subject_id=subj.id, filename="f.pdf", file_hash=uuid.uuid4().hex)
    session.add(doc)
    session.flush()
    ch = Chapter(document_id=doc.id, subject_id=subj.id, title="Ch")
    session.add(ch)
    session.flush()
    top = Topic(chapter_id=ch.id, title="T")
    session.add(top)
    session.flush()
    card = Flashcard(
        topic_id=top.id,
        front="Q",
        back="A",
        ease_factor=ease,
        interval=interval,
        repetitions=reps,
        due_date=due_date,
    )
    session.add(card)
    session.flush()
    return card


def test_correct_new_card_schedules_one_day(session):
    card = _make_card(session)
    review_flashcard(session, card, Grade.correct, today=TODAY)

    assert card.repetitions == 1
    assert card.interval == 1
    assert card.ease_factor == 2.6
    assert card.due_date == TODAY + timedelta(days=1)


def test_incorrect_resets_card(session):
    card = _make_card(session, ease=2.5, interval=16, reps=5)
    review_flashcard(session, card, Grade.incorrect, today=TODAY)

    assert card.repetitions == 0
    assert card.interval == 1
    assert round(card.ease_factor, 2) == 2.18
    assert card.due_date == TODAY + timedelta(days=1)


def test_skip_is_inert(session):
    card = _make_card(session, ease=2.4, interval=6, reps=2, due_date=TODAY - timedelta(days=1))
    before = (card.ease_factor, card.interval, card.repetitions, card.due_date)

    review_flashcard(session, card, Grade.skip, today=TODAY)

    assert (card.ease_factor, card.interval, card.repetitions, card.due_date) == before


def test_deadline_mode_compresses_interval(session):
    # SM-2 would give round(6 * 2.7) = 16 days, but the exam is in 3 days.
    card = _make_card(session, exam_date=TODAY + timedelta(days=3), ease=2.7, interval=6, reps=2)
    review_flashcard(session, card, Grade.correct, today=TODAY)

    assert card.interval == 3
    assert card.due_date == TODAY + timedelta(days=3)


def test_far_exam_does_not_compress(session):
    card = _make_card(session, exam_date=TODAY + timedelta(days=365), ease=2.7, interval=6, reps=2)
    review_flashcard(session, card, Grade.correct, today=TODAY)

    assert card.interval == 16
    assert card.due_date == TODAY + timedelta(days=16)


def test_past_exam_does_not_compress(session):
    card = _make_card(session, exam_date=TODAY - timedelta(days=1), ease=2.7, interval=6, reps=2)
    review_flashcard(session, card, Grade.correct, today=TODAY)

    assert card.interval == 16


def test_no_exam_date_is_standard_sm2(session):
    card = _make_card(session, exam_date=None, ease=2.7, interval=6, reps=2)
    review_flashcard(session, card, Grade.correct, today=TODAY)

    assert card.interval == 16
