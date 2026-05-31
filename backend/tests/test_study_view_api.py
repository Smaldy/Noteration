"""Study View read tests (Phase 9d-1): document tree + topic content."""

from __future__ import annotations

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
    Formula,
    Note,
    Subject,
    Topic,
)
from backend.models.enums import TopicPriority, TopicStatus
from backend.services import documents as docsvc
from backend.services import topics as topicsvc


def _seed_document(db: Session) -> tuple[int, int]:
    """A subject → document → 2 chapters; the first topic gets full content.

    Returns (document_id, content_topic_id). Chapters/topics are inserted out of
    order_index order to prove the service sorts them.
    """
    subject = Subject(name="Physics")
    db.add(subject)
    db.flush()
    document = Document(subject_id=subject.id, filename="lec.pdf", file_hash="h")
    db.add(document)
    db.flush()

    ch1 = Chapter(
        document_id=document.id, subject_id=subject.id, title="Kinematics", order_index=0
    )
    ch2 = Chapter(
        document_id=document.id, subject_id=subject.id, title="Dynamics", order_index=1
    )
    db.add_all([ch2, ch1])  # inserted reversed on purpose
    db.flush()

    t_b = Topic(chapter_id=ch1.id, title="Acceleration", order_index=1)
    t_a = Topic(
        chapter_id=ch1.id,
        title="Velocity",
        order_index=0,
        priority=TopicPriority.exam_critical,
        status=TopicStatus.ready,
    )
    db.add_all([t_b, t_a])  # reversed
    db.flush()

    note = Note(topic_id=t_a.id, content_md="# Velocity\nRate of change of position.")
    db.add(note)
    db.flush()
    db.add(Formula(note_id=note.id, latex="v = dx/dt"))
    db.add(
        MCQ(
            topic_id=t_a.id,
            question="What is velocity?",
            options=["rate of position change", "mass times acceleration"],
            correct_index=0,
            explanation="Definition.",
        )
    )
    db.add(Flashcard(topic_id=t_a.id, front="velocity", back="dx/dt"))
    db.commit()
    return document.id, t_a.id


# --- service unit tests ------------------------------------------------------


def test_get_document_tree_orders_and_groups(session: Session) -> None:
    document_id, _ = _seed_document(session)
    tree = docsvc.get_document_tree(session, document_id)

    assert [c.title for c in tree.chapters] == ["Kinematics", "Dynamics"]
    kinematics = tree.chapters[0]
    assert [t.title for t in kinematics.topics] == ["Velocity", "Acceleration"]
    assert kinematics.topics[0].status == TopicStatus.ready
    assert tree.chapters[1].topics == []


def test_get_document_tree_unknown_raises(session: Session) -> None:
    with pytest.raises(docsvc.DocumentNotFoundError):
        docsvc.get_document_tree(session, 999)


def test_get_topic_content_loads_all(session: Session) -> None:
    _, topic_id = _seed_document(session)
    topic = topicsvc.get_topic_content(session, topic_id)

    assert topic.title == "Velocity"
    assert len(topic.notes) == 1
    assert topic.notes[0].formulas[0].latex == "v = dx/dt"
    assert len(topic.mcqs) == 1
    assert topic.mcqs[0].options == ["rate of position change", "mass times acceleration"]
    assert len(topic.flashcards) == 1


def test_get_topic_content_unknown_raises(session: Session) -> None:
    with pytest.raises(topicsvc.TopicNotFoundError):
        topicsvc.get_topic_content(session, 999)


# --- HTTP tests (shared in-memory DB via StaticPool) ------------------------


@pytest.fixture
def db_factory() -> Generator[sessionmaker, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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


def test_http_document_tree(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        document_id, _ = _seed_document(db)

    response = client.get(f"/api/documents/{document_id}/tree")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["document_id"] == document_id
    assert [c["title"] for c in body["chapters"]] == ["Kinematics", "Dynamics"]
    assert body["chapters"][0]["topics"][0]["title"] == "Velocity"


def test_http_document_tree_404(client: TestClient) -> None:
    assert client.get("/api/documents/999/tree").status_code == 404


def test_http_topic_content(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        _, topic_id = _seed_document(db)

    response = client.get(f"/api/topics/{topic_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Velocity"
    assert body["notes"][0]["formulas"][0]["latex"] == "v = dx/dt"
    assert body["mcqs"][0]["correct_index"] == 0
    assert body["flashcards"][0]["front"] == "velocity"


def test_http_topic_content_404(client: TestClient) -> None:
    assert client.get("/api/topics/999").status_code == 404


# --- delete ------------------------------------------------------------------


def test_delete_topic_cascades_content(session: Session) -> None:
    _, topic_id = _seed_document(session)
    # Sanity: the topic has generated content before deletion.
    assert session.query(Note).filter_by(topic_id=topic_id).count() == 1
    assert session.query(MCQ).filter_by(topic_id=topic_id).count() == 1
    assert session.query(Flashcard).filter_by(topic_id=topic_id).count() == 1

    topicsvc.delete_topic(session, topic_id)

    assert session.get(Topic, topic_id) is None
    assert session.query(Note).filter_by(topic_id=topic_id).count() == 0
    assert session.query(Formula).count() == 0  # note's formula cascaded too
    assert session.query(MCQ).filter_by(topic_id=topic_id).count() == 0
    assert session.query(Flashcard).filter_by(topic_id=topic_id).count() == 0


def test_delete_topic_unknown_raises(session: Session) -> None:
    with pytest.raises(topicsvc.TopicNotFoundError):
        topicsvc.delete_topic(session, 999)


def test_http_delete_topic(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        _, topic_id = _seed_document(db)

    assert client.delete(f"/api/topics/{topic_id}").status_code == 204
    assert client.get(f"/api/topics/{topic_id}").status_code == 404


def test_http_delete_topic_404(client: TestClient) -> None:
    assert client.delete("/api/topics/999").status_code == 404
