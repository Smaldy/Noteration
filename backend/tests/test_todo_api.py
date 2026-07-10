"""To-do list API + the topic studied/completed flag and its calendar sync."""

from __future__ import annotations

import uuid

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models import Chapter, Document, ScheduleEntry, Subject, Topic
from backend.models.hierarchy import utcnow

TODAY = utcnow().date()


def _seed(db_factory, *, topics: int = 3) -> tuple[int, list[int], int]:
    """One subject → document → chapter → N topics. Returns (subject, topic ids, doc)."""
    with db_factory() as db:
        subj = Subject(name="Physics")
        db.add(subj)
        db.flush()
        doc = Document(subject_id=subj.id, filename="f.pdf", file_hash=uuid.uuid4().hex)
        db.add(doc)
        db.flush()
        ch = Chapter(document_id=doc.id, subject_id=subj.id, title="Mechanics")
        db.add(ch)
        db.flush()
        rows = [Topic(chapter_id=ch.id, title=f"Topic {i}") for i in range(topics)]
        db.add_all(rows)
        db.commit()
        return subj.id, [t.id for t in rows], doc.id


# --- studied flag + calendar sync ------------------------------------------ #


def test_set_studied_marks_calendar_sessions(client, db_factory):
    _subj, (topic_id, *_), _doc = _seed(db_factory)
    with db_factory() as db:
        db.add_all(
            [
                ScheduleEntry(topic_id=topic_id, date=TODAY),
                ScheduleEntry(topic_id=topic_id, date=TODAY),
            ]
        )
        db.commit()

    resp = client.put(f"/api/topics/{topic_id}/studied", json={"studied": True})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"id": topic_id, "studied": True}

    with db_factory() as db:
        assert db.get(Topic, topic_id).studied is True
        entries = db.query(ScheduleEntry).filter_by(topic_id=topic_id).all()
        assert all(e.completed and e.completed_at == TODAY for e in entries)

    # Unchecking clears both the flag and every session checkmark.
    resp = client.put(f"/api/topics/{topic_id}/studied", json={"studied": False})
    assert resp.status_code == 200
    with db_factory() as db:
        assert db.get(Topic, topic_id).studied is False
        entries = db.query(ScheduleEntry).filter_by(topic_id=topic_id).all()
        assert all(not e.completed and e.completed_at is None for e in entries)


def test_set_studied_unknown_topic_404(client):
    resp = client.put("/api/topics/999/studied", json={"studied": True})
    assert resp.status_code == 404


def test_checking_one_calendar_session_does_not_flip_topic(client, db_factory):
    """One-way sync: a per-session checkbox never marks the whole topic studied."""
    _subj, (topic_id, *_), _doc = _seed(db_factory)
    with db_factory() as db:
        entry = ScheduleEntry(topic_id=topic_id, date=TODAY)
        db.add(entry)
        db.commit()
        entry_id = entry.id

    resp = client.patch(f"/api/study/schedule/{entry_id}", json={"completed": True})
    assert resp.status_code == 200
    with db_factory() as db:
        assert db.get(Topic, topic_id).studied is False


# --- to-do list CRUD -------------------------------------------------------- #


def test_todo_add_list_and_labels(client, db_factory):
    _subj, topic_ids, doc_id = _seed(db_factory)

    resp = client.post("/api/todo", json={"topic_ids": topic_ids[:2]})
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert [i["topic_id"] for i in items] == topic_ids[:2]
    first = items[0]
    assert first["title"] == "Topic 0"
    assert first["chapter_title"] == "Mechanics"
    assert first["document_id"] == doc_id
    assert first["document_filename"] == "f.pdf"
    assert first["subject_name"] == "Physics"
    assert first["studied"] is False

    assert [i["topic_id"] for i in client.get("/api/todo").json()] == topic_ids[:2]


def test_todo_add_is_idempotent_and_skips_unknown(client, db_factory):
    _subj, topic_ids, _doc = _seed(db_factory)
    client.post("/api/todo", json={"topic_ids": [topic_ids[0]]})
    resp = client.post("/api/todo", json={"topic_ids": [topic_ids[0], 999]})
    assert resp.status_code == 200
    assert [i["topic_id"] for i in resp.json()] == [topic_ids[0]]


def test_todo_item_reflects_studied_flag(client, db_factory):
    _subj, (topic_id, *_), _doc = _seed(db_factory)
    client.post("/api/todo", json={"topic_ids": [topic_id]})
    client.put(f"/api/topics/{topic_id}/studied", json={"studied": True})
    (item,) = client.get("/api/todo").json()
    assert item["studied"] is True


def test_todo_remove_one(client, db_factory):
    _subj, topic_ids, _doc = _seed(db_factory)
    client.post("/api/todo", json={"topic_ids": topic_ids})
    assert client.delete(f"/api/todo/{topic_ids[1]}").status_code == 204
    remaining = [i["topic_id"] for i in client.get("/api/todo").json()]
    assert remaining == [topic_ids[0], topic_ids[2]]
    # Removing again 404s (it's gone).
    assert client.delete(f"/api/todo/{topic_ids[1]}").status_code == 404


def test_todo_clear_completed(client, db_factory):
    _subj, topic_ids, _doc = _seed(db_factory)
    client.post("/api/todo", json={"topic_ids": topic_ids})
    client.put(f"/api/topics/{topic_ids[0]}/studied", json={"studied": True})
    client.put(f"/api/topics/{topic_ids[2]}/studied", json={"studied": True})

    resp = client.delete("/api/todo/completed")
    assert resp.status_code == 200
    assert resp.json() == {"removed": 2}
    remaining = [i["topic_id"] for i in client.get("/api/todo").json()]
    assert remaining == [topic_ids[1]]


def test_todo_item_cascades_with_topic(client, db_factory):
    _subj, (topic_id, *_), _doc = _seed(db_factory)
    client.post("/api/todo", json={"topic_ids": [topic_id]})
    assert client.delete(f"/api/topics/{topic_id}").status_code == 204
    assert client.get("/api/todo").json() == []
