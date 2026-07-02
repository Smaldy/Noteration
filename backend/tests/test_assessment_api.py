"""Aggregated assessment (chapter / document / subject) — service + HTTP."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models import MCQ, Chapter, Document, Flashcard, Subject, Topic
from backend.models.enums import DocumentMode
from backend.services import assessment as asmt


def _topic_with_items(
    session: Session, chapter: Chapter, *, title: str, n_mcq: int, n_card: int
) -> Topic:
    topic = Topic(chapter=chapter, title=title)
    session.add(topic)
    session.flush()
    for i in range(n_mcq):
        session.add(
            MCQ(topic_id=topic.id, question=f"{title} q{i}", options=["a", "b"])
        )
    for i in range(n_card):
        session.add(Flashcard(topic_id=topic.id, front=f"{title} f{i}", back="b"))
    return topic


def _seed(session: Session) -> dict:
    """Subject with two exam docs (+ one study doc) carrying quiz/flashcards."""
    subject = Subject(name="Physics")
    session.add(subject)
    session.flush()

    # Exam doc 1: one chapter, two topics.
    d1 = Document(subject=subject, filename="mech.pdf", file_hash="h1", mode=DocumentMode.exam)
    session.add(d1)
    session.flush()
    ch1 = Chapter(document=d1, subject=subject, title="Mechanics", order_index=0)
    session.add(ch1)
    session.flush()
    _topic_with_items(session, ch1, title="Kinematics", n_mcq=2, n_card=3)
    _topic_with_items(session, ch1, title="Dynamics", n_mcq=1, n_card=1)

    # Exam doc 2: one chapter, one topic.
    d2 = Document(subject=subject, filename="waves.pdf", file_hash="h2", mode=DocumentMode.exam)
    session.add(d2)
    session.flush()
    ch2 = Chapter(document=d2, subject=subject, title="Waves", order_index=0)
    session.add(ch2)
    session.flush()
    _topic_with_items(session, ch2, title="Sound", n_mcq=4, n_card=2)

    # A study doc in the same subject (should be excluded by ?mode=exam).
    d3 = Document(subject=subject, filename="notes.pdf", file_hash="h3", mode=DocumentMode.study)
    session.add(d3)
    session.flush()
    ch3 = Chapter(document=d3, subject=subject, title="Optics", order_index=0)
    session.add(ch3)
    session.flush()
    _topic_with_items(session, ch3, title="Lenses", n_mcq=5, n_card=5)

    session.commit()
    return {"subject": subject.id, "ch1": ch1.id, "ch2": ch2.id, "d1": d1.id, "d3": d3.id}


# --- service ----------------------------------------------------------------


def test_chapter_assessment_pools_its_topics(session: Session) -> None:
    ids = _seed(session)
    agg = asmt.chapter_assessment(session, ids["ch1"])
    assert agg.scope == "chapter" and agg.title == "Mechanics"
    assert agg.topic_count == 2
    assert len(agg.mcqs) == 3  # 2 + 1
    assert len(agg.flashcards) == 4  # 3 + 1


def test_document_assessment_pools_all_chapters(session: Session) -> None:
    ids = _seed(session)
    agg = asmt.document_assessment(session, ids["d1"])
    assert agg.scope == "document"
    assert agg.topic_count == 2
    assert len(agg.mcqs) == 3 and len(agg.flashcards) == 4


def test_subject_assessment_pools_everything(session: Session) -> None:
    ids = _seed(session)
    agg = asmt.subject_assessment(session, ids["subject"])
    # No mode filter → all docs incl. the study one: 3 + 4 mcqs.
    assert len(agg.mcqs) == 2 + 1 + 4 + 5
    assert len(agg.flashcards) == 3 + 1 + 2 + 5


def test_subject_assessment_exam_mode_excludes_study(session: Session) -> None:
    ids = _seed(session)
    agg = asmt.subject_assessment(session, ids["subject"], mode=DocumentMode.exam)
    # Only the two exam docs: (2+1+4) mcqs, (3+1+2) cards.
    assert len(agg.mcqs) == 7
    assert len(agg.flashcards) == 6
    assert agg.topic_count == 3


def _topic_id(session: Session, title: str) -> int:
    return session.scalars(select(Topic.id).where(Topic.title == title)).one()


def test_topics_assessment_pools_selected(session: Session) -> None:
    _seed(session)
    # Pick two topics from different documents of the same subject.
    chosen = [_topic_id(session, "Kinematics"), _topic_id(session, "Sound")]
    agg = asmt.topics_assessment(session, chosen)
    assert agg.scope == "topics"
    assert agg.id == 0
    assert agg.title == "Physics"  # single shared subject → its name
    assert agg.topic_count == 2
    assert len(agg.mcqs) == 2 + 4
    assert len(agg.flashcards) == 3 + 2


def test_topics_assessment_empty_is_empty(session: Session) -> None:
    _seed(session)
    agg = asmt.topics_assessment(session, [])
    assert agg.topic_count == 0 and agg.mcqs == [] and agg.flashcards == []


def test_unknown_scopes_raise(session: Session) -> None:
    with pytest.raises(asmt.ChapterNotFoundError):
        asmt.chapter_assessment(session, 999)
    with pytest.raises(asmt.DocumentNotFoundError):
        asmt.document_assessment(session, 999)
    with pytest.raises(asmt.SubjectNotFoundError):
        asmt.subject_assessment(session, 999)


# --- HTTP -------------------------------------------------------------------


def test_http_subject_assessment_exam_filter(
    client: TestClient, db_factory: sessionmaker
) -> None:
    with db_factory() as db:
        ids = _seed(db)
    resp = client.get(f"/api/assessment/subjects/{ids['subject']}", params={"mode": "exam"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["scope"] == "subject"
    assert len(body["mcqs"]) == 7 and len(body["flashcards"]) == 6


def test_http_chapter_assessment(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        ids = _seed(db)
    body = client.get(f"/api/assessment/chapters/{ids['ch1']}").json()
    assert body["title"] == "Mechanics" and len(body["mcqs"]) == 3


def test_http_assessment_404s(client: TestClient) -> None:
    assert client.get("/api/assessment/chapters/999").status_code == 404
    assert client.get("/api/assessment/documents/999").status_code == 404
    assert client.get("/api/assessment/subjects/999").status_code == 404


def test_http_topics_assessment(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        _seed(db)
        chosen = [_topic_id(db, "Kinematics"), _topic_id(db, "Sound")]
    resp = client.get("/api/assessment/topics", params={"topic_id": chosen})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["scope"] == "topics"
    assert body["topic_count"] == 2
    assert len(body["mcqs"]) == 6 and len(body["flashcards"]) == 5


def test_http_topics_assessment_requires_one(client: TestClient) -> None:
    assert client.get("/api/assessment/topics").status_code == 422
