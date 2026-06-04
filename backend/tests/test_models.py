"""Per-table model tests: persistence, defaults, enums, JSON, and cascades.

One round-trip per table plus the integrity behaviors the data model promises
(denormalized subject_id, SM-2 defaults, single-row Settings, cascade delete
down the Subject→Topic spine, and Note→Formula).
"""

from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    MCQ,
    Chapter,
    Document,
    Flashcard,
    Formula,
    Note,
    ProviderState,
    QueueJob,
    ScheduleEntry,
    Settings,
    SourcePage,
    Subject,
    Topic,
)
from backend.models.enums import (
    DocumentMode,
    DocumentStatus,
    FormulaState,
    QueueLaneState,
    QueueStage,
    QueueState,
    ScheduleSource,
    TopicPriority,
    TopicStatus,
)
from backend.models.settings import SINGLETON_ID


def _make_topic(session: Session) -> Topic:
    """Build a persisted Subject→Document→Chapter→Topic chain."""
    subject = Subject(name="Signals")
    document = Document(subject=subject, filename="lec1.pdf", file_hash="abc123")
    chapter = Chapter(document=document, subject=subject, title="Fourier", order_index=0)
    topic = Topic(chapter=chapter, title="DFT")
    session.add(topic)
    session.commit()
    return topic


def test_subject_roundtrip_and_defaults(session: Session) -> None:
    subject = Subject(name="Control Systems")
    session.add(subject)
    session.commit()
    fetched = session.scalars(select(Subject)).one()
    assert fetched.name == "Control Systems"
    assert fetched.accent_color is None
    assert fetched.exam_date is None
    assert isinstance(fetched.created_at, datetime)


def test_document_status_default_is_uploaded(session: Session) -> None:
    subject = Subject(name="EM")
    doc = Document(subject=subject, filename="a.pdf", file_hash="h")
    session.add(doc)
    session.commit()
    assert doc.status is DocumentStatus.uploaded
    assert isinstance(doc.uploaded_at, datetime)


def test_document_mode_default_is_study(session: Session) -> None:
    subject = Subject(name="EM")
    doc = Document(subject=subject, filename="a.pdf", file_hash="h")
    session.add(doc)
    session.commit()
    assert doc.mode is DocumentMode.study


def test_document_mode_exam_round_trip(session: Session) -> None:
    subject = Subject(name="EM")
    doc = Document(
        subject=subject, filename="a.pdf", file_hash="h", mode=DocumentMode.exam
    )
    session.add(doc)
    session.commit()
    session.expire(doc)
    assert doc.mode is DocumentMode.exam


def test_subject_queue_state_default_is_running(session: Session) -> None:
    subject = Subject(name="Thermo")
    session.add(subject)
    session.commit()
    assert subject.queue_state is QueueLaneState.running


def test_subject_queue_state_round_trip(session: Session) -> None:
    subject = Subject(name="Thermo", queue_state=QueueLaneState.overnight)
    session.add(subject)
    session.commit()
    session.expire(subject)
    assert subject.queue_state is QueueLaneState.overnight


def test_queue_job_subject_id_round_trip_and_cascade(session: Session) -> None:
    topic = _make_topic(session)
    subject_id = topic.chapter.subject_id
    job = QueueJob(
        topic_id=topic.id, subject_id=subject_id, stage=QueueStage.notes
    )
    session.add(job)
    session.commit()
    assert job.subject_id == subject_id
    # Deleting the subject cascades to its denormalized-keyed jobs.
    session.delete(session.get(Subject, subject_id))
    session.commit()
    assert session.scalars(select(QueueJob)).all() == []


def test_chapter_denormalized_subject_id(session: Session) -> None:
    subject = Subject(name="Digital")
    doc = Document(subject=subject, filename="d.pdf", file_hash="h")
    chapter = Chapter(document=doc, subject=subject, title="Boolean", order_index=1)
    session.add(chapter)
    session.commit()
    assert chapter.subject_id == doc.subject_id == subject.id


def test_topic_enum_defaults(session: Session) -> None:
    topic = _make_topic(session)
    assert topic.priority is TopicPriority.medium
    assert topic.status is TopicStatus.queued
    assert topic.studied is False


def test_note_and_formula_roundtrip(session: Session) -> None:
    topic = _make_topic(session)
    note = Note(topic=topic, content_md="# Heading", is_manual=True)
    formula = Formula(note=note, latex=r"\int x\,dx", bbox={"x": 1, "y": 2})
    session.add(formula)
    session.commit()
    assert note.locked is False
    assert note.stale is False
    assert formula.state is FormulaState.reconstructed
    assert formula.confidence is None
    assert formula.bbox == {"x": 1, "y": 2}


def test_mcq_options_json(session: Session) -> None:
    topic = _make_topic(session)
    mcq = MCQ(
        topic=topic,
        question="2+2?",
        options=["3", "4", "5"],
        correct_index=1,
        explanation="basic",
    )
    session.add(mcq)
    session.commit()
    fetched = session.scalars(select(MCQ)).one()
    assert fetched.options == ["3", "4", "5"]
    assert fetched.correct_index == 1


def test_flashcard_sm2_defaults(session: Session) -> None:
    topic = _make_topic(session)
    card = Flashcard(topic=topic, front="Q", back="A")
    session.add(card)
    session.commit()
    assert card.ease_factor == 2.5
    assert card.interval == 0
    assert card.repetitions == 0
    assert card.due_date is None


def test_source_page_roundtrip(session: Session) -> None:
    topic = _make_topic(session)
    page = SourcePage(topic=topic, page_number=7, image_path="/cache/p7.png")
    session.add(page)
    session.commit()
    assert session.scalars(select(SourcePage)).one().page_number == 7


def test_schedule_entry_default_source(session: Session) -> None:
    topic = _make_topic(session)
    entry = ScheduleEntry(topic=topic, date=date(2026, 6, 1))
    session.add(entry)
    session.commit()
    assert entry.source is ScheduleSource.sm2
    assert entry.is_revision_buffer is False


def test_queue_job_defaults_and_updated_at(session: Session) -> None:
    topic = _make_topic(session)
    job = QueueJob(
        topic=topic, subject_id=topic.chapter.subject_id, stage=QueueStage.notes
    )
    session.add(job)
    session.commit()
    assert job.state is QueueState.pending
    assert job.attempts == 0
    assert job.assigned_provider is None
    assert job.resume_after is None
    assert isinstance(job.updated_at, datetime)


def test_provider_state_unique_provider(session: Session) -> None:
    session.add(ProviderState(provider="gemini_free", order_index=0))
    session.commit()
    assert session.scalars(select(ProviderState)).one().enabled is True


def test_settings_singleton_defaults(session: Session) -> None:
    settings = Settings(id=SINGLETON_ID)
    session.add(settings)
    session.commit()
    assert settings.id == 1
    assert settings.allow_paid is False
    assert settings.ollama_enabled is False
    assert settings.pomodoro_work_min == 25
    assert settings.provider_order is None


def test_cascade_delete_subject_removes_descendants(session: Session) -> None:
    topic = _make_topic(session)
    session.add(Note(topic=topic, content_md="x"))
    session.add(MCQ(topic=topic, question="q", options=["a"], correct_index=0))
    session.commit()

    subject = session.scalars(select(Subject)).one()
    session.delete(subject)
    session.commit()

    for model in (Document, Chapter, Topic, Note, MCQ):
        assert session.scalars(select(model)).all() == []


def test_cascade_delete_note_removes_formulas(session: Session) -> None:
    topic = _make_topic(session)
    note = Note(topic=topic, content_md="x")
    note.formulas.append(Formula(latex="a=b"))
    session.add(note)
    session.commit()
    assert session.scalars(select(Formula)).all() != []

    session.delete(note)
    session.commit()
    assert session.scalars(select(Formula)).all() == []


def test_foreign_key_enforced(session: Session) -> None:
    # PRAGMA foreign_keys=ON should reject an orphan topic.
    from sqlalchemy.exc import IntegrityError

    session.add(Topic(chapter_id=999, title="orphan"))
    with pytest.raises(IntegrityError):
        session.commit()
