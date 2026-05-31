"""Reorder tests: manual document (Library) order + topic order within a chapter."""

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
from backend.models import Chapter, Document, Subject, Topic
from backend.services import documents as docsvc
from backend.services import topics as topicsvc


def test_reorder_documents_sets_positions(session: Session) -> None:
    subject = Subject(name="S")
    session.add(subject)
    session.flush()
    docs = [
        Document(subject_id=subject.id, filename=f"{i}.pdf", file_hash=str(i))
        for i in range(3)
    ]
    session.add_all(docs)
    session.commit()
    ids = [docs[2].id, docs[0].id, docs[1].id]

    docsvc.reorder_documents(session, ids)

    assert docsvc.list_documents(session)
    ordered = [s.id for s in docsvc.list_documents(session)]
    assert ordered == ids  # listed in the manual order
    assert session.get(Document, ids[0]).order_index == 0
    assert session.get(Document, ids[2]).order_index == 2


def test_new_upload_sorts_to_front(session: Session) -> None:
    subject = Subject(name="S")
    session.add(subject)
    session.flush()
    a = Document(subject_id=subject.id, filename="a.pdf", file_hash="a")
    session.add(a)
    session.commit()
    docsvc.reorder_documents(session, [a.id])  # a → order_index 0

    # A freshly created document gets a smaller index, so it sorts to the front.
    min_order = session.query(Document.order_index).order_by(
        Document.order_index.asc()
    ).first()[0]
    new = Document(
        subject_id=subject.id,
        filename="b.pdf",
        file_hash="b",
        order_index=min_order - 1,
    )
    session.add(new)
    session.commit()
    ordered = [s.id for s in docsvc.list_documents(session)]
    assert ordered[0] == new.id


def test_reorder_topics_sets_positions(session: Session) -> None:
    subject = Subject(name="S")
    session.add(subject)
    session.flush()
    doc = Document(subject_id=subject.id, filename="d.pdf", file_hash="h")
    session.add(doc)
    session.flush()
    chapter = Chapter(document_id=doc.id, subject_id=subject.id, title="Ch")
    session.add(chapter)
    session.flush()
    topics = [Topic(chapter_id=chapter.id, title=f"T{i}") for i in range(3)]
    session.add_all(topics)
    session.commit()
    ids = [topics[2].id, topics[1].id, topics[0].id]

    topicsvc.reorder_topics(session, ids)

    tree = docsvc.get_document_tree(session, doc.id)
    assert [t.id for t in tree.chapters[0].topics] == ids


# --- HTTP --------------------------------------------------------------------


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


def test_http_reorder_documents(client: TestClient, db_factory: sessionmaker) -> None:
    seed = db_factory()
    subject = Subject(name="S")
    seed.add(subject)
    seed.flush()
    docs = [
        Document(subject_id=subject.id, filename=f"{i}.pdf", file_hash=str(i))
        for i in range(3)
    ]
    seed.add_all(docs)
    seed.commit()
    ids = [docs[1].id, docs[2].id, docs[0].id]
    seed.close()

    r = client.put("/api/documents/reorder", json={"ids": ids})
    assert r.status_code == 204, r.text

    listed = [d["id"] for d in client.get("/api/documents").json()]
    assert listed == ids


def test_http_reorder_topics(client: TestClient, db_factory: sessionmaker) -> None:
    seed = db_factory()
    subject = Subject(name="S")
    seed.add(subject)
    seed.flush()
    doc = Document(subject_id=subject.id, filename="d.pdf", file_hash="h")
    seed.add(doc)
    seed.flush()
    chapter = Chapter(document_id=doc.id, subject_id=subject.id, title="Ch")
    seed.add(chapter)
    seed.flush()
    topics = [Topic(chapter_id=chapter.id, title=f"T{i}") for i in range(3)]
    seed.add_all(topics)
    seed.commit()
    doc_id = doc.id
    ids = [topics[2].id, topics[0].id, topics[1].id]
    seed.close()

    r = client.put("/api/topics/reorder", json={"ids": ids})
    assert r.status_code == 204, r.text

    tree = client.get(f"/api/documents/{doc_id}/tree").json()
    assert [t["id"] for t in tree["chapters"][0]["topics"]] == ids
