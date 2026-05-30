"""Phase 8d — study API: review queue, self-grading, calendar."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.db.database import get_session
from backend.main import app
from backend.models import Chapter, Document, Flashcard, Subject, Topic

TODAY = date.today()
D = timedelta(days=1)


@pytest.fixture
def client(session) -> TestClient:
    app.dependency_overrides[get_session] = lambda: session
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def _make_card(session, *, exam_date=None, due_date=None, ease=2.5, interval=0, reps=0):
    subj = Subject(name="Math", exam_date=exam_date)
    session.add(subj)
    session.flush()
    doc = Document(subject_id=subj.id, filename="f.pdf", file_hash=uuid.uuid4().hex)
    session.add(doc)
    session.flush()
    ch = Chapter(document_id=doc.id, subject_id=subj.id, title="Ch")
    session.add(ch)
    session.flush()
    top = Topic(chapter_id=ch.id, title="T")
    session.add(top)
    session.flush()
    card = Flashcard(
        topic_id=top.id,
        front="Q",
        back="A",
        ease_factor=ease,
        interval=interval,
        repetitions=reps,
        due_date=due_date,
    )
    session.add(card)
    session.commit()
    return card


def test_due_endpoint_reviews_then_new(client, session):
    overdue = _make_card(session, due_date=TODAY - 2 * D)
    _make_card(session, due_date=TODAY + 5 * D)  # future: excluded
    new = _make_card(session, due_date=None)

    resp = client.get("/api/study/due")
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == [overdue.id, new.id]


def test_due_endpoint_limit(client, session):
    _make_card(session, due_date=TODAY - 2 * D)
    _make_card(session, due_date=TODAY - 1 * D)
    _make_card(session, due_date=None)

    resp = client.get("/api/study/due", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_review_correct_schedules_and_returns_card(client, session):
    card = _make_card(session)

    resp = client.post(
        f"/api/study/flashcards/{card.id}/review", json={"grade": "correct"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["repetitions"] == 1
    assert body["interval"] == 1
    assert body["ease_factor"] == pytest.approx(2.6)
    assert body["due_date"] == (TODAY + D).isoformat()


def test_review_skip_is_inert(client, session):
    card = _make_card(session, due_date=TODAY - D, ease=2.4, interval=6, reps=2)

    resp = client.post(
        f"/api/study/flashcards/{card.id}/review", json={"grade": "skip"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval"] == 6
    assert body["repetitions"] == 2
    assert body["due_date"] == (TODAY - D).isoformat()


def test_review_unknown_flashcard_404(client):
    resp = client.post("/api/study/flashcards/99999/review", json={"grade": "correct"})
    assert resp.status_code == 404


def test_review_invalid_grade_422(client, session):
    card = _make_card(session)
    resp = client.post(
        f"/api/study/flashcards/{card.id}/review", json={"grade": "maybe"}
    )
    assert resp.status_code == 422


def test_review_materialises_calendar(client, session):
    card = _make_card(session)
    client.post(f"/api/study/flashcards/{card.id}/review", json={"grade": "correct"})

    resp = client.get(
        "/api/study/calendar",
        params={"start": TODAY.isoformat(), "end": (TODAY + 30 * D).isoformat()},
    )
    assert resp.status_code == 200
    entries = resp.json()
    assert len(entries) == 1
    assert entries[0]["date"] == (TODAY + D).isoformat()
    assert entries[0]["source"] == "sm2"
    assert entries[0]["is_revision_buffer"] is False


def test_calendar_bad_range_422(client):
    resp = client.get(
        "/api/study/calendar",
        params={"start": (TODAY + 5 * D).isoformat(), "end": TODAY.isoformat()},
    )
    assert resp.status_code == 422
