"""On-demand notes regeneration — service + prompt + HTTP.

Regenerating a topic's notes rewrites ONLY the AI note (the quiz/flashcards and
their SM-2 state survive), respects the per-note lock, refuses on exam docs, and
re-stamps the notes-stage provider so the Study View provenance stays accurate.
"""

from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app
from backend.models import (
    MCQ,
    Chapter,
    Document,
    Flashcard,
    Note,
    QueueJob,
    Subject,
    Topic,
)
from backend.models.enums import DocumentMode, QueueStage
from backend.services import topics as topicsvc
from backend.services.pipeline.generation import (
    GenerationParseError,
    build_regenerate_notes_prompt,
    notes_only_max_tokens,
    parse_notes_only,
)
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall

_NEW_NOTES = json.dumps({"notes_md": "## Rolling\n\nFresh, improved notes on torque."})


def _seed_topic(session: Session, tmp_path, *, mode: DocumentMode = DocumentMode.study) -> Topic:
    md = tmp_path / "doc.md"
    md.write_text("# Rolling\n\nTorque is r cross F.\n", encoding="utf-8")
    subject = Subject(name="Physics")
    document = Document(
        subject=subject, filename="f.pdf", file_hash="h", markdown_path=str(md), mode=mode
    )
    chapter = Chapter(document=document, subject=subject, title="Mechanics")
    topic = Topic(chapter=chapter, title="Rolling")
    session.add_all([subject, document, chapter, topic])
    session.commit()
    return topic


# --- prompt / parsing -------------------------------------------------------


def test_parse_notes_only_valid() -> None:
    assert parse_notes_only(_NEW_NOTES).startswith("## Rolling")


def test_parse_notes_only_rejects_missing() -> None:
    with pytest.raises(GenerationParseError):
        parse_notes_only(json.dumps({"mcqs": []}))


def test_regenerate_prompt_includes_instructions() -> None:
    plain = build_regenerate_notes_prompt("Rolling", "src")
    assert "What to improve" not in plain
    guided = build_regenerate_notes_prompt(
        "Rolling", "src", instructions="Add a worked example."
    )
    assert "What to improve" in guided
    assert "Add a worked example." in guided


def test_notes_only_cap_below_full_generation() -> None:
    # Notes-only drops the assessment tokens, so it must cost less headroom.
    from backend.services.pipeline.generation import study_max_tokens

    assert notes_only_max_tokens(3) < study_max_tokens(3)


# --- service ----------------------------------------------------------------


def test_regenerate_replaces_notes_keeps_assessment(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path)
    note = Note(topic_id=topic.id, content_md="old notes", is_manual=False)
    mcq = MCQ(topic_id=topic.id, question="q?", options=["a", "b"])
    card = Flashcard(
        topic_id=topic.id, front="f", back="b", interval=9, repetitions=3, ease_factor=2.8
    )
    session.add_all([note, mcq, card])
    session.commit()

    waterfall = Waterfall([MockProvider("gemini_free", text=_NEW_NOTES)])
    topicsvc.regenerate_notes(session, topic.id, waterfall=waterfall)

    session.refresh(note)
    assert "Fresh, improved" in note.content_md  # rewritten
    assert note.stale is True  # assessment now predates the notes
    # Assessment is untouched — counts and SM-2 state preserved.
    assert session.query(MCQ).filter_by(topic_id=topic.id).count() == 1
    session.refresh(card)
    assert card.interval == 9 and card.repetitions == 3 and card.ease_factor == 2.8


def test_regenerate_creates_note_when_none(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path)
    waterfall = Waterfall([MockProvider("gemini_free", text=_NEW_NOTES)])
    topicsvc.regenerate_notes(session, topic.id, waterfall=waterfall)

    notes = session.query(Note).filter_by(topic_id=topic.id, is_manual=False).all()
    assert len(notes) == 1 and "Fresh, improved" in notes[0].content_md


def test_regenerate_restamps_provider(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path)
    job = QueueJob(
        topic_id=topic.id,
        subject_id=topic.chapter.subject_id,
        stage=QueueStage.notes,
        assigned_provider="old_provider",
    )
    session.add(job)
    session.commit()

    waterfall = Waterfall([MockProvider("gemini_free", text=_NEW_NOTES)])
    topicsvc.regenerate_notes(session, topic.id, waterfall=waterfall)

    session.refresh(job)
    assert job.assigned_provider == "gemini_free"


def test_regenerate_locked_note_refused(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path)
    note = Note(topic_id=topic.id, content_md="locked notes", is_manual=False, locked=True)
    session.add(note)
    session.commit()

    waterfall = Waterfall([MockProvider("gemini_free", text=_NEW_NOTES)])
    with pytest.raises(topicsvc.NoteLockedError):
        topicsvc.regenerate_notes(session, topic.id, waterfall=waterfall)
    session.refresh(note)
    assert note.content_md == "locked notes"  # unchanged


def test_regenerate_exam_doc_refused(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path, mode=DocumentMode.exam)
    waterfall = Waterfall([MockProvider("gemini_free", text=_NEW_NOTES)])
    with pytest.raises(topicsvc.NotesNotSupportedError):
        topicsvc.regenerate_notes(session, topic.id, waterfall=waterfall)


def test_regenerate_unknown_topic_raises(session: Session) -> None:
    waterfall = Waterfall([MockProvider("gemini_free", text=_NEW_NOTES)])
    with pytest.raises(topicsvc.TopicNotFoundError):
        topicsvc.regenerate_notes(session, 999, waterfall=waterfall)


def test_regenerate_malformed_keeps_old(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path)
    note = Note(topic_id=topic.id, content_md="old notes", is_manual=False)
    session.add(note)
    session.commit()

    waterfall = Waterfall([MockProvider("gemini_free", text="not json")])
    with pytest.raises(GenerationParseError):
        topicsvc.regenerate_notes(session, topic.id, waterfall=waterfall)
    session.refresh(note)
    assert note.content_md == "old notes"  # nothing written


# --- HTTP -------------------------------------------------------------------


@pytest.fixture
def db_factory() -> Generator[sessionmaker, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record) -> None:  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(db_factory: sessionmaker) -> Generator[TestClient, None, None]:
    def _override() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_http_regenerate_404(client: TestClient) -> None:
    resp = client.post("/api/topics/999/notes/regenerate", json={})
    assert resp.status_code == 404


def test_http_regenerate_locked_409(client: TestClient, db_factory: sessionmaker, tmp_path) -> None:
    db = db_factory()
    topic = _seed_topic(db, tmp_path)
    db.add(Note(topic_id=topic.id, content_md="x", is_manual=False, locked=True))
    db.commit()
    topic_id = topic.id
    db.close()

    resp = client.post(f"/api/topics/{topic_id}/notes/regenerate", json={})
    assert resp.status_code == 409
