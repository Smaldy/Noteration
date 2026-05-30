"""Phase 9a — Library document-list service + API (progress, ordering)."""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app
from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import DocumentStatus, TopicStatus
from backend.models.hierarchy import utcnow
from backend.services import documents as docsvc


def _subject(session, *, name="Math", exam_date=None) -> Subject:
    subj = Subject(name=name, exam_date=exam_date)
    session.add(subj)
    session.flush()
    return subj


def _document(session, subject, *, filename="f.pdf", status=DocumentStatus.uploaded,
              uploaded_at=None) -> Document:
    doc = Document(
        subject_id=subject.id,
        filename=filename,
        file_hash=uuid.uuid4().hex,
        status=status,
    )
    if uploaded_at is not None:
        doc.uploaded_at = uploaded_at
    session.add(doc)
    session.flush()
    return doc


def _topic(session, document, subject, *, status=TopicStatus.queued) -> Topic:
    ch = Chapter(document_id=document.id, subject_id=subject.id, title="Ch")
    session.add(ch)
    session.flush()
    top = Topic(chapter_id=ch.id, title="T", status=status)
    session.add(top)
    session.flush()
    return top


# --- service tests (in-memory `session` fixture) ----------------------------


def test_list_empty(session: Session):
    assert docsvc.list_documents(session) == []


def test_list_document_without_topics_reports_zero(session: Session):
    subj = _subject(session, exam_date=date(2026, 6, 1))
    _document(session, subj, filename="intro.pdf")

    [summary] = docsvc.list_documents(session)
    assert summary.filename == "intro.pdf"
    assert summary.subject_name == "Math"
    assert summary.exam_date == date(2026, 6, 1)
    assert summary.topics_total == 0
    assert summary.topics_ready == 0


def test_list_counts_ready_topics(session: Session):
    subj = _subject(session)
    doc = _document(session, subj)
    _topic(session, doc, subj, status=TopicStatus.ready)
    _topic(session, doc, subj, status=TopicStatus.ready)
    _topic(session, doc, subj, status=TopicStatus.queued)
    _topic(session, doc, subj, status=TopicStatus.error)

    [summary] = docsvc.list_documents(session)
    assert summary.topics_total == 4
    assert summary.topics_ready == 2


def test_list_orders_newest_first(session: Session):
    subj = _subject(session)
    now = utcnow()
    _document(session, subj, filename="old.pdf", uploaded_at=now - timedelta(days=2))
    _document(session, subj, filename="new.pdf", uploaded_at=now)
    _document(session, subj, filename="mid.pdf", uploaded_at=now - timedelta(days=1))

    names = [s.filename for s in docsvc.list_documents(session)]
    assert names == ["new.pdf", "mid.pdf", "old.pdf"]


def test_list_counts_are_per_document(session: Session):
    subj = _subject(session)
    doc_a = _document(session, subj, filename="a.pdf")
    doc_b = _document(session, subj, filename="b.pdf")
    _topic(session, doc_a, subj, status=TopicStatus.ready)
    _topic(session, doc_b, subj, status=TopicStatus.queued)

    by_name = {s.filename: s for s in docsvc.list_documents(session)}
    assert (by_name["a.pdf"].topics_total, by_name["a.pdf"].topics_ready) == (1, 1)
    assert (by_name["b.pdf"].topics_total, by_name["b.pdf"].topics_ready) == (1, 0)


# --- HTTP test (shared in-memory DB via StaticPool) -------------------------


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


def test_get_documents_endpoint(client: TestClient, db_factory: sessionmaker):
    with db_factory() as db:
        subj = _subject(db, name="Physics", exam_date=date(2026, 7, 1))
        doc = _document(db, subj, filename="mechanics.pdf",
                        status=DocumentStatus.processing)
        _topic(db, doc, subj, status=TopicStatus.ready)
        _topic(db, doc, subj, status=TopicStatus.queued)
        db.commit()

    resp = client.get("/api/documents")
    assert resp.status_code == 200
    [body] = resp.json()
    assert body["filename"] == "mechanics.pdf"
    assert body["subject_name"] == "Physics"
    assert body["exam_date"] == "2026-07-01"
    assert body["status"] == "processing"
    assert body["topics_total"] == 2
    assert body["topics_ready"] == 1


def test_get_documents_empty(client: TestClient):
    assert client.get("/api/documents").json() == []
