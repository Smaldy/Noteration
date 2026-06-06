"""Bookmark toggle + aggregation tests (subjects and topics)."""

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
from backend.services import bookmarks as bookmarks_service
from backend.services import subjects as subjectsvc
from backend.services import topics as topicsvc


def _seed(session: Session) -> dict[str, int]:
    subject = Subject(name="Physics")
    session.add(subject)
    session.flush()
    doc = Document(subject_id=subject.id, filename="p.pdf", file_hash="h")
    session.add(doc)
    session.flush()
    chapter = Chapter(document_id=doc.id, subject_id=subject.id, title="Mechanics")
    session.add(chapter)
    session.flush()
    topic = Topic(chapter_id=chapter.id, title="Kinematics")
    session.add(topic)
    session.commit()
    return {"subject": subject.id, "topic": topic.id, "doc": doc.id}


# --- service units -----------------------------------------------------------


def test_set_subject_bookmark_toggles(session: Session) -> None:
    ids = _seed(session)
    subjectsvc.set_bookmark(session, ids["subject"], bookmarked=True)
    assert session.get(Subject, ids["subject"]).bookmarked is True
    subjectsvc.set_bookmark(session, ids["subject"], bookmarked=False)
    assert session.get(Subject, ids["subject"]).bookmarked is False


def test_set_topic_bookmark_toggles(session: Session) -> None:
    ids = _seed(session)
    topicsvc.set_bookmark(session, ids["topic"], bookmarked=True)
    assert session.get(Topic, ids["topic"]).bookmarked is True


def test_set_bookmark_missing_raises(session: Session) -> None:
    with pytest.raises(subjectsvc.SubjectNotFoundError):
        subjectsvc.set_bookmark(session, 999, bookmarked=True)
    with pytest.raises(topicsvc.TopicNotFoundError):
        topicsvc.set_bookmark(session, 999, bookmarked=True)


def test_list_bookmarks_returns_marked_only(session: Session) -> None:
    ids = _seed(session)
    assert bookmarks_service.list_bookmarks(session).subjects == []
    subjectsvc.set_bookmark(session, ids["subject"], bookmarked=True)
    topicsvc.set_bookmark(session, ids["topic"], bookmarked=True)

    result = bookmarks_service.list_bookmarks(session)
    assert [s.id for s in result.subjects] == [ids["subject"]]
    # Bookmarked subject carries its primary document for deep-linking.
    assert result.subjects[0].document_id == ids["doc"]
    assert len(result.topics) == 1
    hit = result.topics[0]
    assert hit.id == ids["topic"]
    assert hit.subject_name == "Physics"
    assert hit.chapter_title == "Mechanics"
    assert hit.document_id == ids["doc"]


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


def test_http_bookmark_subject_and_aggregate(
    client: TestClient, db_factory: sessionmaker
) -> None:
    seed = db_factory()
    ids = _seed(seed)
    seed.close()

    r = client.put(f"/api/subjects/{ids['subject']}/bookmark", json={"bookmarked": True})
    assert r.status_code == 200, r.text
    assert r.json()["bookmarked"] is True

    r = client.put(f"/api/topics/{ids['topic']}/bookmark", json={"bookmarked": True})
    assert r.status_code == 200, r.text
    assert r.json() == {"id": ids["topic"], "bookmarked": True}

    bm = client.get("/api/bookmarks").json()
    assert [s["id"] for s in bm["subjects"]] == [ids["subject"]]
    assert bm["subjects"][0]["document_id"] == ids["doc"]
    assert [t["id"] for t in bm["topics"]] == [ids["topic"]]

    # The library row reflects the subject bookmark.
    lib = client.get("/api/documents").json()
    assert lib[0]["subject_bookmarked"] is True


def test_http_bookmark_404(client: TestClient) -> None:
    assert client.put("/api/subjects/999/bookmark", json={"bookmarked": True}).status_code == 404
    assert client.put("/api/topics/999/bookmark", json={"bookmarked": True}).status_code == 404
