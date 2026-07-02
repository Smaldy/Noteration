"""Topic merge — content re-pointing, SM-2 preservation, notes, HTTP endpoint.

The fix for per-lesson PDFs piling up parallel topics on one subject: a target
topic absorbs sources (cross-document allowed), moving quiz/flashcard progress
untouched, appending AI notes under per-source headings, and deleting the
emptied sources. Consolidation is a best-effort single model call.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models import (
    MCQ,
    Chapter,
    Document,
    Flashcard,
    Note,
    ScheduleEntry,
    Subject,
    Topic,
)
from backend.services import topics as topicsvc
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall


def _seed(session: Session) -> tuple[Topic, Topic]:
    """Two documents in one subject, each with one topic (lesson-per-PDF shape)."""
    subject = Subject(name="Physics")
    doc1 = Document(subject=subject, filename="lesson1.pdf", file_hash="h1")
    doc2 = Document(subject=subject, filename="lesson2.pdf", file_hash="h2")
    ch1 = Chapter(document=doc1, subject=subject, title="Lesson 1")
    ch2 = Chapter(document=doc2, subject=subject, title="Lesson 2")
    target = Topic(chapter=ch1, title="Rolling motion")
    source = Topic(chapter=ch2, title="Rolling (continued)")
    session.add_all([subject, doc1, doc2, ch1, ch2, target, source])
    session.add_all(
        [
            Note(topic=target, content_md="Target notes.", is_manual=False),
            Note(topic=source, content_md="Source notes.", is_manual=False),
            Note(topic=source, content_md="My own remark.", is_manual=True),
            MCQ(topic=source, question="Q?", options=["a", "b"], correct_index=0),
            Flashcard(
                topic=source,
                front="F",
                back="B",
                ease_factor=2.1,
                interval=6,
                repetitions=3,
                due_date=date.today() + timedelta(days=2),
            ),
        ]
    )
    session.commit()
    return target, source


def test_merge_moves_content_and_preserves_sm2(session: Session) -> None:
    target, source = _seed(session)
    source_id = source.id

    consolidated = topicsvc.merge_topics(session, target.id, [source_id])

    assert consolidated is False
    assert session.get(Topic, source_id) is None  # source deleted
    mcq = session.scalars(select(MCQ)).one()
    assert mcq.topic_id == target.id
    card = session.scalars(select(Flashcard)).one()
    assert card.topic_id == target.id
    # SM-2 state travels untouched — the whole point of re-pointing, not copying.
    assert (card.ease_factor, card.interval, card.repetitions) == (2.1, 6, 3)

    manual = session.scalars(select(Note).where(Note.is_manual.is_(True))).one()
    assert manual.topic_id == target.id
    ai_note = session.scalars(select(Note).where(Note.is_manual.is_(False))).one()
    assert ai_note.topic_id == target.id
    assert ai_note.content_md == (
        "Target notes.\n\n## Rolling (continued)\n\nSource notes."
    )


def test_merge_rebuilds_schedule_under_target(session: Session) -> None:
    target, source = _seed(session)
    topicsvc.merge_topics(session, target.id, [source.id], today=date.today())
    entries = session.scalars(select(ScheduleEntry)).all()
    assert entries and all(e.topic_id == target.id for e in entries)


def test_merge_unions_pdf_pages_same_document_only(session: Session) -> None:
    target, cross_source = _seed(session)
    target.pdf_pages = [1, 2]
    cross_source.pdf_pages = [3]  # other document → must NOT union
    same_chapter = session.get(Chapter, target.chapter_id)
    same_source = Topic(
        chapter=same_chapter, title="Rolling energy", pdf_pages=[4, 2]
    )
    session.add(same_source)
    session.commit()

    topicsvc.merge_topics(session, target.id, [cross_source.id, same_source.id])
    assert session.get(Topic, target.id).pdf_pages == [1, 2, 4]


def test_merge_rejects_self_and_unknown(session: Session) -> None:
    target, source = _seed(session)
    with pytest.raises(topicsvc.InvalidMergeError):
        topicsvc.merge_topics(session, target.id, [target.id])
    with pytest.raises(topicsvc.TopicNotFoundError):
        topicsvc.merge_topics(session, target.id, [99999])
    with pytest.raises(topicsvc.TopicNotFoundError):
        topicsvc.merge_topics(session, 99999, [source.id])


def test_merge_consolidates_notes_via_one_call(session: Session) -> None:
    target, source = _seed(session)
    provider = MockProvider(
        "gemini", text=json.dumps({"notes_md": "## Rolling\n\nOne clean note."})
    )
    consolidated = topicsvc.merge_topics(
        session,
        target.id,
        [source.id],
        consolidate=True,
        waterfall=Waterfall(providers=[provider]),
    )
    assert consolidated is True
    assert provider.generate_calls == 1
    # The concatenation (with both notes) went into the prompt; the rewrite wins.
    assert "Target notes." in provider.last_prompt
    assert "Source notes." in provider.last_prompt
    note = session.scalars(select(Note).where(Note.is_manual.is_(False))).one()
    assert note.content_md == "## Rolling\n\nOne clean note."


def test_merge_survives_failed_consolidation(session: Session) -> None:
    target, source = _seed(session)
    provider = MockProvider("gemini", raises=RuntimeError("down"))
    consolidated = topicsvc.merge_topics(
        session,
        target.id,
        [source.id],
        consolidate=True,
        waterfall=Waterfall(providers=[provider]),
    )
    # The merge itself committed; the concatenated notes stand.
    assert consolidated is False
    note = session.scalars(select(Note).where(Note.is_manual.is_(False))).one()
    assert "Target notes." in note.content_md
    assert "Source notes." in note.content_md


def test_merge_skips_consolidation_when_note_locked(session: Session) -> None:
    target, source = _seed(session)
    note = session.scalars(select(Note).where(Note.topic_id == target.id)).one()
    note.locked = True
    session.commit()
    provider = MockProvider("gemini", text=json.dumps({"notes_md": "REWRITTEN"}))
    consolidated = topicsvc.merge_topics(
        session,
        target.id,
        [source.id],
        consolidate=True,
        waterfall=Waterfall(providers=[provider]),
    )
    assert consolidated is False
    assert provider.generate_calls == 0  # locked notes are never rewritten


def test_merge_never_rewrites_locked_target_note(session: Session) -> None:
    target, source = _seed(session)
    locked = session.scalars(select(Note).where(Note.topic_id == target.id)).one()
    locked.locked = True
    session.commit()
    locked_id = locked.id

    topicsvc.merge_topics(session, target.id, [source.id])

    # The locked note's text is untouched; the source note moved as its own note.
    assert session.get(Note, locked_id).content_md == "Target notes."
    moved = session.scalars(
        select(Note).where(
            Note.topic_id == target.id,
            Note.is_manual.is_(False),
            Note.id != locked_id,
        )
    ).one()
    assert moved.content_md == "## Rolling (continued)\n\nSource notes."


# --- HTTP --------------------------------------------------------------------


def test_merge_endpoint(client: TestClient, db_factory: sessionmaker) -> None:
    db = db_factory()
    target, source = _seed(db)
    target_id, source_id = target.id, source.id
    db.close()

    response = client.post(
        f"/api/topics/{target_id}/merge",
        json={"source_topic_ids": [source_id]},
    )
    assert response.status_code == 204

    body = client.get(f"/api/topics/{target_id}").json()
    assert body["id"] == target_id
    assert len(body["mcqs"]) == 1
    assert len(body["flashcards"]) == 1
    assert "## Rolling (continued)" in body["notes"][0]["content_md"]

    missing = client.post(
        f"/api/topics/{target_id}/merge", json={"source_topic_ids": [target_id]}
    )
    assert missing.status_code == 400
