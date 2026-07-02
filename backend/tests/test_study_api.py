"""Phase 8d — study API: review queue, self-grading, calendar.

Uses a shared in-memory DB across threads (StaticPool) with a `get_session`
override, mirroring test_documents_api.py — the TestClient runs requests on a
worker thread, so a plain per-connection in-memory DB would be empty there.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models import Chapter, Document, Flashcard, Subject, Topic
from backend.models.hierarchy import utcnow

# Match the server's UTC convention (routers.study._today == utcnow().date());
# local date.today() can be a day off near midnight in non-UTC timezones.
TODAY = utcnow().date()
D = timedelta(days=1)


def _make_card(
    db_factory, *, exam_date=None, due_date=None, ease=2.5, interval=0, reps=0
) -> int:
    with db_factory() as db:
        subj = Subject(name="Math", exam_date=exam_date)
        db.add(subj)
        db.flush()
        doc = Document(subject_id=subj.id, filename="f.pdf", file_hash=uuid.uuid4().hex)
        db.add(doc)
        db.flush()
        ch = Chapter(document_id=doc.id, subject_id=subj.id, title="Ch")
        db.add(ch)
        db.flush()
        top = Topic(chapter_id=ch.id, title="T")
        db.add(top)
        db.flush()
        card = Flashcard(
            topic_id=top.id,
            front="Q",
            back="A",
            ease_factor=ease,
            interval=interval,
            repetitions=reps,
            due_date=due_date,
        )
        db.add(card)
        db.commit()
        return card.id


def test_due_endpoint_reviews_then_new(client, db_factory):
    overdue = _make_card(db_factory, due_date=TODAY - 2 * D)
    _make_card(db_factory, due_date=TODAY + 5 * D)  # future: excluded
    new = _make_card(db_factory, due_date=None)

    resp = client.get("/api/study/due")
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == [overdue, new]


def test_due_endpoint_limit(client, db_factory):
    _make_card(db_factory, due_date=TODAY - 2 * D)
    _make_card(db_factory, due_date=TODAY - 1 * D)
    _make_card(db_factory, due_date=None)

    resp = client.get("/api/study/due", params={"limit": 2})
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_review_correct_schedules_and_returns_card(client, db_factory):
    card_id = _make_card(db_factory)

    resp = client.post(
        f"/api/study/flashcards/{card_id}/review", json={"grade": "correct"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["repetitions"] == 1
    assert body["interval"] == 1
    assert body["ease_factor"] == pytest.approx(2.6)
    assert body["due_date"] == (TODAY + D).isoformat()


def test_review_skip_is_inert(client, db_factory):
    card_id = _make_card(db_factory, due_date=TODAY - D, ease=2.4, interval=6, reps=2)

    resp = client.post(
        f"/api/study/flashcards/{card_id}/review", json={"grade": "skip"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval"] == 6
    assert body["repetitions"] == 2
    assert body["due_date"] == (TODAY - D).isoformat()


def test_review_unknown_flashcard_404(client):
    resp = client.post("/api/study/flashcards/99999/review", json={"grade": "correct"})
    assert resp.status_code == 404


def test_review_invalid_grade_422(client, db_factory):
    card_id = _make_card(db_factory)
    resp = client.post(
        f"/api/study/flashcards/{card_id}/review", json={"grade": "maybe"}
    )
    assert resp.status_code == 422


def test_review_materialises_calendar(client, db_factory):
    card_id = _make_card(db_factory)
    client.post(f"/api/study/flashcards/{card_id}/review", json={"grade": "correct"})

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


def test_calendar_includes_topic_title(client, db_factory):
    card_id = _make_card(db_factory)
    client.post(f"/api/study/flashcards/{card_id}/review", json={"grade": "correct"})
    resp = client.get(
        "/api/study/calendar",
        params={"start": TODAY.isoformat(), "end": (TODAY + 30 * D).isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()[0]["topic_title"] == "T"


def test_reschedule_moves_entry_to_manual(client, db_factory):
    card_id = _make_card(db_factory)
    client.post(f"/api/study/flashcards/{card_id}/review", json={"grade": "correct"})
    entries = client.get(
        "/api/study/calendar",
        params={"start": TODAY.isoformat(), "end": (TODAY + 30 * D).isoformat()},
    ).json()
    entry_id = entries[0]["id"]

    new_date = (TODAY + 10 * D).isoformat()
    resp = client.patch(f"/api/study/schedule/{entry_id}", json={"date": new_date})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["date"] == new_date
    assert body["source"] == "manual"


def test_reschedule_unknown_404(client):
    resp = client.patch("/api/study/schedule/999", json={"date": TODAY.isoformat()})
    assert resp.status_code == 404
