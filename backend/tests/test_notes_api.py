"""Note editing — service + HTTP (edit, lock, add manual block, delete)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models import (
    Chapter,
    Document,
    Formula,
    Note,
    Subject,
    Topic,
)
from backend.services import notes as notesvc


def _seed_topic(session: Session) -> dict:
    """A subject→document→chapter→topic with one AI note carrying a formula."""
    subject = Subject(name="Physics")
    session.add(subject)
    session.flush()
    doc = Document(subject=subject, filename="m.pdf", file_hash="h1")
    session.add(doc)
    session.flush()
    chapter = Chapter(document=doc, subject=subject, title="Mechanics", order_index=0)
    session.add(chapter)
    session.flush()
    topic = Topic(chapter=chapter, title="Kinematics")
    session.add(topic)
    session.flush()
    note = Note(topic_id=topic.id, content_md="Original $v = u + at$.")
    session.add(note)
    session.flush()
    session.add(Formula(note_id=note.id, latex="v = u + at"))
    session.commit()
    return {"topic": topic.id, "note": note.id}


# --- service ----------------------------------------------------------------


def test_update_note_changes_content(session: Session) -> None:
    ids = _seed_topic(session)
    note = notesvc.update_note(session, ids["note"], content_md="Edited body.")
    assert note.content_md == "Edited body."
    assert note.is_manual is False  # editing an AI note doesn't make it manual
    assert len(note.formulas) == 1  # formulas still load for serialization


def test_update_note_partial_keeps_other_fields(session: Session) -> None:
    ids = _seed_topic(session)
    notesvc.update_note(session, ids["note"], locked=True)
    note = session.get(Note, ids["note"])
    assert note.locked is True
    assert note.content_md == "Original $v = u + at$."  # untouched


def test_create_manual_note(session: Session) -> None:
    ids = _seed_topic(session)
    note = notesvc.create_manual_note(session, ids["topic"], "My own note.")
    assert note.is_manual is True
    assert note.content_md == "My own note."
    assert note.topic_id == ids["topic"]


def test_delete_note_removes_it_and_formulas(session: Session) -> None:
    ids = _seed_topic(session)
    notesvc.delete_note(session, ids["note"])
    assert session.get(Note, ids["note"]) is None
    assert session.query(Formula).count() == 0  # cascaded


def test_unknown_ids_raise(session: Session) -> None:
    with pytest.raises(notesvc.NoteNotFoundError):
        notesvc.update_note(session, 999, content_md="x")
    with pytest.raises(notesvc.NoteNotFoundError):
        notesvc.delete_note(session, 999)
    with pytest.raises(notesvc.TopicNotFoundError):
        notesvc.create_manual_note(session, 999, "x")


# --- HTTP -------------------------------------------------------------------


def test_http_patch_note(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        ids = _seed_topic(db)
    resp = client.patch(f"/api/notes/{ids['note']}", json={"content_md": "New text."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["content_md"] == "New text."
    assert len(body["formulas"]) == 1


def test_http_post_manual_note(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        ids = _seed_topic(db)
    resp = client.post(
        "/api/notes", json={"topic_id": ids["topic"], "content_md": "Manual."}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_manual"] is True and body["content_md"] == "Manual."


def test_http_delete_note(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        ids = _seed_topic(db)
    assert client.delete(f"/api/notes/{ids['note']}").status_code == 204


def test_http_404s(client: TestClient) -> None:
    assert client.patch("/api/notes/999", json={"content_md": "x"}).status_code == 404
    assert client.delete("/api/notes/999").status_code == 404
    assert (
        client.post("/api/notes", json={"topic_id": 999, "content_md": "x"}).status_code
        == 404
    )
