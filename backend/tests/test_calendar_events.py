"""Calendar manual + custom events: create/edit/complete/delete + topic catalog.

Shared in-memory DB across threads (StaticPool) with a `get_session` override,
mirroring test_study_api.py (the TestClient runs on a worker thread).
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app
from backend.models import Chapter, Document, ScheduleEntry, Subject, Topic
from backend.models.hierarchy import utcnow

# Match the server's UTC convention (routers.study._today == utcnow().date());
# local date.today() can be a day off near midnight in non-UTC timezones.
TODAY = utcnow().date()
D = timedelta(days=1)


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


def _seed(db_factory) -> tuple[int, int, int]:
    """One subject → document → chapter → topic. Returns (subject, topic, doc) ids."""
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
        top = Topic(chapter_id=ch.id, title="Torque")
        db.add(top)
        db.commit()
        return subj.id, top.id, doc.id


# --- create ---------------------------------------------------------------- #


def test_create_custom_event(client):
    resp = client.post(
        "/api/study/schedule",
        json={"date": TODAY.isoformat(), "title": "Review week", "description": "deep work"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "custom"
    assert body["title"] == "Review week"
    assert body["description"] == "deep work"
    assert body["source"] == "manual"
    assert body["topic_id"] is None and body["subject_id"] is None


def test_create_topic_session_carries_navigation(client, db_factory):
    _subj, topic_id, doc_id = _seed(db_factory)
    resp = client.post(
        "/api/study/schedule", json={"date": TODAY.isoformat(), "topic_id": topic_id}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "topic"
    assert body["topic_id"] == topic_id
    assert body["topic_title"] == "Torque"
    assert body["document_id"] == doc_id
    assert body["title"] == "Torque"  # default display = topic title


def test_create_subject_session(client, db_factory):
    subj_id, _topic, _doc = _seed(db_factory)
    resp = client.post(
        "/api/study/schedule", json={"date": TODAY.isoformat(), "subject_id": subj_id}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "subject"
    assert body["subject_id"] == subj_id
    assert body["title"] == "Study Physics"


def test_create_requires_something(client):
    resp = client.post("/api/study/schedule", json={"date": TODAY.isoformat()})
    assert resp.status_code == 422


def test_create_unknown_topic_404(client):
    resp = client.post(
        "/api/study/schedule", json={"date": TODAY.isoformat(), "topic_id": 999}
    )
    assert resp.status_code == 404


# --- start time (hourly scheduling) ----------------------------------------- #


def test_create_with_start_time(client):
    resp = client.post(
        "/api/study/schedule",
        json={"date": TODAY.isoformat(), "title": "Morning block", "start_time": "09:30"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["start_time"] == "09:30"


def test_create_without_time_is_all_day(client):
    resp = client.post(
        "/api/study/schedule", json={"date": TODAY.isoformat(), "title": "Whenever"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["start_time"] is None


def test_set_then_clear_start_time(client):
    entry = client.post(
        "/api/study/schedule", json={"date": TODAY.isoformat(), "title": "X"}
    ).json()
    set_resp = client.patch(
        f"/api/study/schedule/{entry['id']}", json={"start_time": "14:00"}
    )
    assert set_resp.json()["start_time"] == "14:00"
    # Explicit null clears it back to all-day.
    cleared = client.patch(
        f"/api/study/schedule/{entry['id']}", json={"start_time": None}
    )
    assert cleared.json()["start_time"] is None


def test_omitting_start_time_leaves_it_unchanged(client):
    entry = client.post(
        "/api/study/schedule",
        json={"date": TODAY.isoformat(), "title": "X", "start_time": "08:15"},
    ).json()
    # A title-only edit must not wipe the previously-set time.
    body = client.patch(
        f"/api/study/schedule/{entry['id']}", json={"title": "Renamed"}
    ).json()
    assert body["start_time"] == "08:15"


# --- complete / on-time ----------------------------------------------------- #


def test_complete_on_time(client):
    entry = client.post(
        "/api/study/schedule", json={"date": TODAY.isoformat(), "title": "Today"}
    ).json()
    resp = client.patch(f"/api/study/schedule/{entry['id']}", json={"completed": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["completed"] is True
    assert body["completed_at"] == TODAY.isoformat()
    assert body["on_time"] is True


def test_complete_late(client):
    past = (TODAY - 5 * D).isoformat()
    entry = client.post(
        "/api/study/schedule", json={"date": past, "title": "Overdue"}
    ).json()
    body = client.patch(
        f"/api/study/schedule/{entry['id']}", json={"completed": True}
    ).json()
    assert body["completed"] is True
    assert body["on_time"] is False  # completed today, was due 5 days ago


def test_uncomplete_clears(client):
    entry = client.post(
        "/api/study/schedule", json={"date": TODAY.isoformat(), "title": "X"}
    ).json()
    client.patch(f"/api/study/schedule/{entry['id']}", json={"completed": True})
    body = client.patch(
        f"/api/study/schedule/{entry['id']}", json={"completed": False}
    ).json()
    assert body["completed"] is False
    assert body["completed_at"] is None
    assert body["on_time"] is None


def test_edit_title_and_description(client):
    entry = client.post(
        "/api/study/schedule", json={"date": TODAY.isoformat(), "title": "X"}
    ).json()
    body = client.patch(
        f"/api/study/schedule/{entry['id']}",
        json={"title": "Renamed", "description": "notes"},
    ).json()
    assert body["title"] == "Renamed"
    assert body["description"] == "notes"


# --- delete ----------------------------------------------------------------- #


def test_delete_entry(client):
    entry = client.post(
        "/api/study/schedule", json={"date": TODAY.isoformat(), "title": "X"}
    ).json()
    assert client.delete(f"/api/study/schedule/{entry['id']}").status_code == 204
    assert client.delete(f"/api/study/schedule/{entry['id']}").status_code == 404


# --- topic catalog ---------------------------------------------------------- #


# --- deadline / exam markers ----------------------------------------------- #


def _subject_exam_date(db_factory, subject_id: int):
    with db_factory() as db:
        return db.get(Subject, subject_id).exam_date


def test_create_deadline_sets_subject_exam_date(client, db_factory):
    subj_id, _topic, _doc = _seed(db_factory)
    exam = (TODAY + 14 * D).isoformat()
    resp = client.post(
        "/api/study/schedule",
        json={"date": exam, "subject_id": subj_id, "title": "Final", "is_deadline": True},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["kind"] == "deadline"
    assert body["is_deadline"] is True
    assert _subject_exam_date(db_factory, subj_id).isoformat() == exam


def test_deadline_requires_subject_422(client):
    resp = client.post(
        "/api/study/schedule",
        json={"date": TODAY.isoformat(), "title": "Exam", "is_deadline": True},
    )
    assert resp.status_code == 422


def test_move_deadline_updates_exam_date(client, db_factory):
    subj_id, _t, _d = _seed(db_factory)
    entry = client.post(
        "/api/study/schedule",
        json={"date": (TODAY + 10 * D).isoformat(), "subject_id": subj_id, "is_deadline": True},
    ).json()
    moved = (TODAY + 20 * D).isoformat()
    client.patch(f"/api/study/schedule/{entry['id']}", json={"date": moved})
    assert _subject_exam_date(db_factory, subj_id).isoformat() == moved


def test_delete_deadline_clears_exam_date(client, db_factory):
    subj_id, _t, _d = _seed(db_factory)
    entry = client.post(
        "/api/study/schedule",
        json={"date": (TODAY + 10 * D).isoformat(), "subject_id": subj_id, "is_deadline": True},
    ).json()
    assert client.delete(f"/api/study/schedule/{entry['id']}").status_code == 204
    assert _subject_exam_date(db_factory, subj_id) is None


# --- delete an AI plan ------------------------------------------------------ #


def test_delete_plan_removes_ai_entries(client, db_factory):
    subj_id, topic_id, _doc = _seed(db_factory)
    with db_factory() as db:
        db.add_all(
            [
                ScheduleEntry(topic_id=topic_id, date=TODAY + 1 * D, source="ai"),
                ScheduleEntry(topic_id=topic_id, date=TODAY + 2 * D, source="ai"),
                ScheduleEntry(topic_id=topic_id, date=TODAY + 3 * D, source="manual"),
            ]
        )
        db.commit()
    resp = client.delete(f"/api/study/plan/{subj_id}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2
    with db_factory() as db:
        remaining = db.query(ScheduleEntry).all()
        assert [e.source.value for e in remaining] == ["manual"]


# --- AI plan endpoint (error paths; happy path covered in test_planner.py) -- #


def test_plan_unknown_subject_404(client):
    resp = client.post("/api/study/plan", json={"subject_id": 999})
    assert resp.status_code == 404


def test_plan_no_topics_409(client, db_factory):
    with db_factory() as db:
        subj = Subject(name="Empty")
        db.add(subj)
        db.commit()
        subj_id = subj.id
    resp = client.post("/api/study/plan", json={"subject_id": subj_id})
    assert resp.status_code == 409


def test_plan_no_provider_503(client, db_factory):
    subj_id, _topic, _doc = _seed(db_factory)  # has a topic, but no API key configured
    resp = client.post("/api/study/plan", json={"subject_id": subj_id})
    assert resp.status_code == 503


def test_topic_catalog_groups_by_subject(client, db_factory):
    subj_id, topic_id, doc_id = _seed(db_factory)
    resp = client.get("/api/study/topic-catalog")
    assert resp.status_code == 200
    catalog = resp.json()
    assert len(catalog) == 1
    subject = catalog[0]
    assert subject["id"] == subj_id
    assert subject["name"] == "Physics"
    assert len(subject["topics"]) == 1
    topic = subject["topics"][0]
    assert topic["id"] == topic_id
    assert topic["title"] == "Torque"
    assert topic["chapter_title"] == "Mechanics"
    assert topic["document_id"] == doc_id
    assert topic["studied"] is False
