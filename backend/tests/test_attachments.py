"""Note-attachment tests: manual image/audio attached to a topic's notes (Wave 5)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app
from backend.models import Chapter, Document, NoteAttachment, Subject, Topic
from backend.services import attachments as attachsvc


def _topic(session: Session) -> Topic:
    subject = Subject(name="Physics")
    session.add(subject)
    session.flush()
    document = Document(subject_id=subject.id, filename="d.pdf", file_hash="h")
    session.add(document)
    session.flush()
    chapter = Chapter(document_id=document.id, subject_id=subject.id, title="C")
    session.add(chapter)
    session.flush()
    topic = Topic(chapter_id=chapter.id, title="T")
    session.add(topic)
    session.commit()
    return topic


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(attachsvc, "ATTACHMENTS_DIR", tmp_path / "attachments")


# --- service ----------------------------------------------------------------


def test_add_image_attachment(session: Session) -> None:
    topic = _topic(session)
    att = attachsvc.add_attachment(
        session,
        topic.id,
        filename="diagram.png",
        content_type="image/png",
        data=b"\x89PNG-bytes",
    )
    assert att.kind == "image"
    assert attachsvc.attachment_path(att).is_file()
    assert attachsvc.attachment_url(att) == f"/api/attachments/{att.id}/file"


def test_add_audio_attachment(session: Session) -> None:
    topic = _topic(session)
    att = attachsvc.add_attachment(
        session,
        topic.id,
        filename="clip.mp3",
        content_type="audio/mpeg",
        data=b"audio",
    )
    assert att.kind == "audio"


def test_reject_non_media(session: Session) -> None:
    topic = _topic(session)
    with pytest.raises(attachsvc.UnsupportedAttachmentError):
        attachsvc.add_attachment(
            session,
            topic.id,
            filename="notes.pdf",
            content_type="application/pdf",
            data=b"%PDF",
        )


def test_reject_empty(session: Session) -> None:
    topic = _topic(session)
    with pytest.raises(attachsvc.UnsupportedAttachmentError):
        attachsvc.add_attachment(
            session, topic.id, filename="x.png", content_type="image/png", data=b""
        )


def test_add_to_unknown_topic_raises(session: Session) -> None:
    with pytest.raises(attachsvc.TopicNotFoundError):
        attachsvc.add_attachment(
            session, 999, filename="x.png", content_type="image/png", data=b"x"
        )


def test_topic_content_includes_attachments(session: Session) -> None:
    from backend.services.topics import get_topic_content

    topic = _topic(session)
    attachsvc.add_attachment(
        session, topic.id, filename="a.png", content_type="image/png", data=b"img"
    )
    loaded = get_topic_content(session, topic.id)
    assert len(loaded.attachments) == 1
    assert loaded.attachments[0].url.endswith("/file")


def test_delete_removes_row_and_file(session: Session) -> None:
    topic = _topic(session)
    att = attachsvc.add_attachment(
        session, topic.id, filename="a.png", content_type="image/png", data=b"img"
    )
    path = attachsvc.attachment_path(att)
    attachsvc.delete_attachment(session, att.id)
    assert session.get(NoteAttachment, att.id) is None
    assert not path.is_file()


def test_delete_keeps_file_shared_by_another(session: Session) -> None:
    topic = _topic(session)
    # Same bytes uploaded twice → same content hash / file, two rows.
    a1 = attachsvc.add_attachment(
        session, topic.id, filename="a.png", content_type="image/png", data=b"same"
    )
    a2 = attachsvc.add_attachment(
        session, topic.id, filename="b.png", content_type="image/png", data=b"same"
    )
    assert a1.file_hash == a2.file_hash
    attachsvc.delete_attachment(session, a1.id)
    # a2 still references the file, so it must survive.
    assert attachsvc.attachment_path(a2).is_file()


def test_delete_unknown_raises(session: Session) -> None:
    with pytest.raises(attachsvc.AttachmentNotFoundError):
        attachsvc.delete_attachment(session, 999)


def test_attachment_cascades_with_topic(session: Session) -> None:
    topic = _topic(session)
    attachsvc.add_attachment(
        session, topic.id, filename="a.png", content_type="image/png", data=b"img"
    )
    session.delete(topic)
    session.commit()
    assert session.scalar(select(NoteAttachment)) is None


# --- HTTP (shared in-memory DB via StaticPool) ------------------------------


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


def test_http_attachment_roundtrip(
    client: TestClient, db_factory: sessionmaker
) -> None:
    with db_factory() as db:
        topic = _topic(db)
        topic_id = topic.id

    # Upload
    up = client.post(
        f"/api/topics/{topic_id}/attachments",
        files={"file": ("pic.png", b"\x89PNG-data", "image/png")},
    )
    assert up.status_code == 201, up.text
    body = up.json()
    assert body["kind"] == "image"
    att_id = body["id"]

    # It shows up in the topic content
    content = client.get(f"/api/topics/{topic_id}").json()
    assert any(a["id"] == att_id for a in content["attachments"])

    # Serve the file
    served = client.get(f"/api/attachments/{att_id}/file")
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")
    assert served.content == b"\x89PNG-data"

    # Delete it
    assert client.delete(f"/api/attachments/{att_id}").status_code == 204
    assert client.get(f"/api/attachments/{att_id}/file").status_code == 404


def test_http_reject_non_media(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        topic = _topic(db)
        topic_id = topic.id
    resp = client.post(
        f"/api/topics/{topic_id}/attachments",
        files={"file": ("x.pdf", b"%PDF", "application/pdf")},
    )
    assert resp.status_code == 400


def test_http_attach_unknown_topic_404(client: TestClient) -> None:
    resp = client.post(
        "/api/topics/999/attachments",
        files={"file": ("x.png", b"img", "image/png")},
    )
    assert resp.status_code == 404
