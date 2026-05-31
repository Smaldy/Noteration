"""Subject service + HTTP tests (Phase 9c-1): list + create."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app
from backend.models import Chapter, Document, Note, Subject, Topic
from backend.models.enums import QueueStage
from backend.models.processing import QueueJob
from backend.services import subjects as subjectsvc

# --- service unit tests ------------------------------------------------------


def test_create_subject_persists_and_trims(session: Session) -> None:
    subject = subjectsvc.create_subject(
        session, name="  Thermodynamics  ", exam_date=date(2026, 6, 15)
    )
    assert subject.id is not None
    assert subject.name == "Thermodynamics"  # trimmed
    assert subject.exam_date == date(2026, 6, 15)
    assert subject.created_at is not None


def test_create_subject_defaults(session: Session) -> None:
    subject = subjectsvc.create_subject(session, name="Statics")
    assert subject.accent_color is None
    assert subject.exam_date is None


def test_list_subjects_sorted_case_insensitive(session: Session) -> None:
    subjectsvc.create_subject(session, name="dynamics")
    subjectsvc.create_subject(session, name="Algebra")
    subjectsvc.create_subject(session, name="Beams")

    names = [s.name for s in subjectsvc.list_subjects(session)]
    assert names == ["Algebra", "Beams", "dynamics"]


def test_list_subjects_empty(session: Session) -> None:
    assert subjectsvc.list_subjects(session) == []


def test_delete_subject_cascades_whole_hierarchy(session: Session) -> None:
    subject = Subject(name="Physics")
    document = Document(subject=subject, filename="f.pdf", file_hash="h")
    session.add_all([subject, document])
    session.flush()
    chapter = Chapter(
        document_id=document.id, subject_id=subject.id, title="Mechanics", order_index=0
    )
    session.add(chapter)
    session.flush()
    topic = Topic(chapter_id=chapter.id, title="Kinematics", order_index=0)
    session.add(topic)
    session.flush()
    session.add_all(
        [
            Note(topic_id=topic.id, content_md="x"),
            QueueJob(topic_id=topic.id, stage=QueueStage.notes),
        ]
    )
    session.commit()

    subjectsvc.delete_subject(session, subject.id)

    assert session.get(Subject, subject.id) is None
    assert session.query(Document).count() == 0
    assert session.query(Chapter).count() == 0
    assert session.query(Topic).count() == 0
    assert session.query(Note).count() == 0
    assert session.query(QueueJob).count() == 0


def test_delete_subject_unknown_raises(session: Session) -> None:
    with pytest.raises(subjectsvc.SubjectNotFoundError):
        subjectsvc.delete_subject(session, 999)


# --- HTTP tests (shared in-memory DB via StaticPool) ------------------------


@pytest.fixture
def db_factory() -> Generator[sessionmaker, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared in-memory connection across threads
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


def test_post_subject_returns_201(client: TestClient) -> None:
    response = client.post(
        "/api/subjects", json={"name": "Fluid Mechanics", "exam_date": "2026-07-01"}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "Fluid Mechanics"
    assert body["exam_date"] == "2026-07-01"
    assert body["accent_color"] is None


def test_post_subject_rejects_blank_name(client: TestClient) -> None:
    response = client.post("/api/subjects", json={"name": ""})
    assert response.status_code == 422


def test_get_subjects_lists_created(
    client: TestClient, db_factory: sessionmaker
) -> None:
    with db_factory() as db:
        db.add_all([Subject(name="Zeta"), Subject(name="alpha")])
        db.commit()

    response = client.get("/api/subjects")
    assert response.status_code == 200
    names = [s["name"] for s in response.json()]
    assert names == ["alpha", "Zeta"]  # case-insensitive sort


def test_http_delete_subject(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        db.add(Subject(name="Doomed"))
        db.commit()
        subject_id = db.query(Subject).one().id

    assert client.delete(f"/api/subjects/{subject_id}").status_code == 204
    assert client.get("/api/subjects").json() == []


def test_http_delete_subject_404(client: TestClient) -> None:
    assert client.delete("/api/subjects/999").status_code == 404
