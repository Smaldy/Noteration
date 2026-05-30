"""Phase 8c — ScheduleEntry calendar materialisation + study queue."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from backend.models import Chapter, Document, Flashcard, ScheduleEntry, Subject, Topic
from backend.models.enums import ScheduleSource
from backend.services.scheduler import due_flashcards, rebuild_schedule

TODAY = date(2026, 1, 1)
D = timedelta(days=1)


def _subject(session, *, exam_date=None):
    subj = Subject(name="S", exam_date=exam_date)
    session.add(subj)
    session.flush()
    doc = Document(subject_id=subj.id, filename="f.pdf", file_hash=uuid.uuid4().hex)
    session.add(doc)
    session.flush()
    ch = Chapter(document_id=doc.id, subject_id=subj.id, title="C")
    session.add(ch)
    session.flush()
    return subj, ch


def _topic(session, ch, title="T"):
    t = Topic(chapter_id=ch.id, title=title)
    session.add(t)
    session.flush()
    return t


def _card(session, topic, due_date):
    c = Flashcard(topic_id=topic.id, front="q", back="a", due_date=due_date)
    session.add(c)
    session.flush()
    return c


def _entries(session, topic_id):
    return session.scalars(
        scheduler_select(ScheduleEntry, topic_id)
    ).all()


def scheduler_select(model, topic_id):
    from sqlalchemy import select

    return select(model).where(model.topic_id == topic_id).order_by(model.date)


def test_rebuild_standard_one_entry_per_topic_date(session):
    subj, ch = _subject(session)
    t1 = _topic(session, ch, "T1")
    _card(session, t1, TODAY + 1 * D)
    _card(session, t1, TODAY + 5 * D)
    t2 = _topic(session, ch, "T2")
    _card(session, t2, TODAY + 1 * D)

    entries = rebuild_schedule(session, subj, today=TODAY)
    session.flush()

    assert len(entries) == 3
    assert all(e.source == ScheduleSource.sm2 for e in entries)
    assert all(e.is_revision_buffer is False for e in entries)


def test_rebuild_dedupes_same_topic_date(session):
    subj, ch = _subject(session)
    t = _topic(session, ch)
    _card(session, t, TODAY + 2 * D)
    _card(session, t, TODAY + 2 * D)  # same date, second card

    entries = rebuild_schedule(session, subj, today=TODAY)
    assert [e.date for e in entries] == [TODAY + 2 * D]


def test_rebuild_ignores_unscheduled_cards(session):
    subj, ch = _subject(session)
    t = _topic(session, ch)
    _card(session, t, None)  # never scheduled

    assert rebuild_schedule(session, subj, today=TODAY) == []


def test_deadline_mode_flags_revision_buffer(session):
    exam = TODAY + 3 * D
    subj, ch = _subject(session, exam_date=exam)
    t = _topic(session, ch)
    _card(session, t, TODAY + 1 * D)  # outside buffer
    _card(session, t, TODAY + 2 * D)  # buffer (exam - 1)
    _card(session, t, TODAY + 3 * D)  # buffer (exam day)

    entries = rebuild_schedule(session, subj, today=TODAY)
    by_date = {e.date: e for e in entries}

    assert all(e.source == ScheduleSource.deadline for e in entries)
    assert by_date[TODAY + 1 * D].is_revision_buffer is False
    assert by_date[TODAY + 2 * D].is_revision_buffer is True
    assert by_date[TODAY + 3 * D].is_revision_buffer is True


def test_rebuild_preserves_manual_replaces_machine(session):
    subj, ch = _subject(session)
    t = _topic(session, ch)
    _card(session, t, TODAY + 1 * D)
    manual = ScheduleEntry(
        topic_id=t.id, date=TODAY + 10 * D, source=ScheduleSource.manual
    )
    stale = ScheduleEntry(topic_id=t.id, date=TODAY + 99 * D, source=ScheduleSource.sm2)
    session.add_all([manual, stale])
    session.flush()

    rebuild_schedule(session, subj, today=TODAY)
    session.commit()

    rows = _entries(session, t.id)
    dates = sorted(r.date for r in rows)
    assert dates == [TODAY + 1 * D, TODAY + 10 * D]  # new sm2 + preserved manual
    sources = {r.date: r.source for r in rows}
    assert sources[TODAY + 10 * D] == ScheduleSource.manual
    assert sources[TODAY + 1 * D] == ScheduleSource.sm2


def test_due_flashcards_reviews_then_new(session):
    subj, ch = _subject(session)
    t = _topic(session, ch)
    overdue = _card(session, t, TODAY - 2 * D)
    due_today = _card(session, t, TODAY)
    _card(session, t, TODAY + 5 * D)  # future: excluded
    new1 = _card(session, t, None)

    due = due_flashcards(session, today=TODAY)
    assert [c.id for c in due] == [overdue.id, due_today.id, new1.id]


def test_due_flashcards_limit(session):
    subj, ch = _subject(session)
    t = _topic(session, ch)
    _card(session, t, TODAY - 2 * D)
    _card(session, t, TODAY - 1 * D)
    _card(session, t, None)

    assert len(due_flashcards(session, today=TODAY, limit=2)) == 2
