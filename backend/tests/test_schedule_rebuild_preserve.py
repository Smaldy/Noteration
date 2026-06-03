"""rebuild_schedule preserves user-owned (manual/ai) entries and carries the
completion checkmark forward onto regenerated SM-2 slots."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from backend.models import Chapter, Document, Flashcard, ScheduleEntry, Subject, Topic
from backend.models.enums import ScheduleSource
from backend.services import scheduler

TODAY = date.today()
D = timedelta(days=1)


def _seed(session):
    subj = Subject(name="Physics")
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
    card = Flashcard(topic_id=top.id, front="Q", back="A", due_date=TODAY + 3 * D)
    session.add(card)
    session.commit()
    return subj, top


def test_rebuild_preserves_manual_and_ai(session):
    subj, top = _seed(session)
    session.add_all(
        [
            ScheduleEntry(topic_id=top.id, date=TODAY + 1 * D, source=ScheduleSource.manual),
            ScheduleEntry(topic_id=top.id, date=TODAY + 2 * D, source=ScheduleSource.ai),
        ]
    )
    session.commit()

    scheduler.rebuild_schedule(session, subj, today=TODAY)
    session.commit()

    sources = sorted(e.source.value for e in session.query(ScheduleEntry).all())
    # manual + ai survive; one sm2 entry materialised from the card's due date.
    assert sources == ["ai", "manual", "sm2"]


def test_rebuild_carries_completion_forward(session):
    subj, top = _seed(session)
    # An auto SM-2 entry on the card's due date, checked off as studied.
    entry = ScheduleEntry(
        topic_id=top.id,
        date=TODAY + 3 * D,
        source=ScheduleSource.sm2,
        completed=True,
        completed_at=TODAY,
    )
    session.add(entry)
    session.commit()

    scheduler.rebuild_schedule(session, subj, today=TODAY)
    session.commit()

    regenerated = session.query(ScheduleEntry).filter_by(date=TODAY + 3 * D).one()
    assert regenerated.completed is True
    assert regenerated.completed_at == TODAY
