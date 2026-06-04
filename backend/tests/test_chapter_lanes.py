"""Chapter Lanes & Lazy Ingestion — Wave 3.

Confirm persists per-chapter ``queue_state`` + page ranges and enqueues only
non-paused chapters' topics; the queue gains chapter pause/resume (rollback +
lazy enqueue) and never claims a paused chapter's jobs; the PATCH endpoint drives
it. Service tests use the in-memory ``session``; the HTTP test uses StaticPool.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base, get_session
from backend.main import app
from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import (
    QueueLaneState,
    QueueStage,
    QueueState,
    TopicPriority,
    TopicStatus,
)
from backend.models.processing import QueueJob
from backend.schemas.structure import ChapterIn, TopicIn
from backend.services import documents as docsvc
from backend.services.queue import QueueService


def _confirm(session: Session, chapters: list[ChapterIn]) -> Document:
    subject = Subject(name="Physics")
    document = Document(subject=subject, filename="f.pdf", file_hash="h")
    session.add_all([subject, document])
    session.commit()
    docsvc.confirm_structure(session, document.id, chapters=chapters)
    return document


# --- confirm: paused vs running ---------------------------------------------


def test_confirm_paused_chapter_creates_topics_but_no_jobs(session: Session) -> None:
    _confirm(
        session,
        [
            ChapterIn(
                title="Chapter 1",
                queue_state=QueueLaneState.paused,
                page_start=12,
                page_end=79,
                topics=[TopicIn(title="T1"), TopicIn(title="T2")],
            )
        ],
    )
    chapter = session.scalars(select(Chapter)).one()
    assert chapter.queue_state is QueueLaneState.paused
    # Page ranges persisted onto the chapter row.
    assert (chapter.page_start, chapter.page_end) == (12, 79)
    # Topics exist in the tree...
    assert len(session.scalars(select(Topic)).all()) == 2
    # ...but a paused chapter creates zero queue jobs.
    assert session.scalars(select(QueueJob)).all() == []


def test_confirm_running_chapter_enqueues(session: Session) -> None:
    _confirm(
        session,
        [
            ChapterIn(
                title="Chapter 1",
                queue_state=QueueLaneState.running,
                topics=[TopicIn(title="T1")],
            )
        ],
    )
    jobs = session.scalars(select(QueueJob)).all()
    assert {j.stage for j in jobs} == {QueueStage.formula, QueueStage.notes}


# --- resume / pause ---------------------------------------------------------


def test_resume_chapter_enqueues_previously_paused(session: Session) -> None:
    _confirm(
        session,
        [
            ChapterIn(
                title="Chapter 1",
                queue_state=QueueLaneState.paused,
                topics=[
                    TopicIn(title="T1"),
                    TopicIn(title="Appendix", priority=TopicPriority.skip),
                ],
            )
        ],
    )
    assert session.scalars(select(QueueJob)).all() == []

    chapter = session.scalars(select(Chapter)).one()
    QueueService(session).resume_chapter(chapter.id)

    assert session.get(Chapter, chapter.id).queue_state is QueueLaneState.running
    t1 = session.scalars(select(Topic).where(Topic.title == "T1")).one()
    jobs = session.scalars(select(QueueJob)).all()
    # Only the non-skip topic is enqueued on resume.
    assert {j.topic_id for j in jobs} == {t1.id}


def test_resume_chapter_does_not_duplicate_existing_jobs(session: Session) -> None:
    # A chapter confirmed running already has jobs; resuming it must not re-enqueue.
    _confirm(
        session,
        [
            ChapterIn(
                title="Chapter 1",
                queue_state=QueueLaneState.running,
                topics=[TopicIn(title="T1")],
            )
        ],
    )
    before = len(session.scalars(select(QueueJob)).all())
    chapter = session.scalars(select(Chapter)).one()
    QueueService(session).resume_chapter(chapter.id)
    assert len(session.scalars(select(QueueJob)).all()) == before


def test_pause_chapter_rolls_back_inflight_jobs(session: Session) -> None:
    _confirm(
        session,
        [
            ChapterIn(
                title="Chapter 1",
                queue_state=QueueLaneState.running,
                topics=[TopicIn(title="T1")],
            )
        ],
    )
    # Simulate a job claimed and assigned (in-flight) before the pause.
    job = session.scalars(select(QueueJob)).first()
    job.state = QueueState.running
    job.assigned_provider = "gemini_free"
    session.commit()

    chapter = session.scalars(select(Chapter)).one()
    QueueService(session).pause_chapter(chapter.id)

    refreshed = session.get(QueueJob, job.id)
    assert refreshed.state is QueueState.pending  # rolled back to queued
    assert refreshed.assigned_provider is None


def test_claim_next_never_claims_a_paused_chapter(session: Session) -> None:
    _confirm(
        session,
        [
            ChapterIn(
                title="ChA",
                queue_state=QueueLaneState.running,
                topics=[TopicIn(title="A1")],
            ),
            ChapterIn(
                title="ChB",
                queue_state=QueueLaneState.running,
                topics=[TopicIn(title="B1")],
            ),
        ],
    )
    queue = QueueService(session)
    chapter_b = session.scalars(select(Chapter).where(Chapter.title == "ChB")).one()
    queue.pause_chapter(chapter_b.id)
    b_topic_ids = {
        t.id for t in session.scalars(
            select(Topic).where(Topic.chapter_id == chapter_b.id)
        ).all()
    }

    claimed: list[int] = []
    for _ in range(20):
        job = queue.claim_next()
        if job is None:
            break
        claimed.append(job.topic_id)

    assert claimed  # ChA still dispatches
    assert all(topic_id not in b_topic_ids for topic_id in claimed)


# --- GET /api/documents/{id}/chapters/status --------------------------------


def test_chapter_statuses_counts_and_state(session: Session) -> None:
    document = _confirm(
        session,
        [
            ChapterIn(
                title="ChA",
                queue_state=QueueLaneState.running,
                page_start=12,
                page_end=79,
                topics=[TopicIn(title="A1"), TopicIn(title="A2")],
            ),
            ChapterIn(
                title="ChB",
                queue_state=QueueLaneState.paused,
                topics=[TopicIn(title="B1")],
            ),
        ],
    )
    a_topics = session.scalars(
        select(Topic).where(Topic.title.in_(["A1", "A2"]))
    ).all()
    a_topics[0].status = TopicStatus.ready
    a_topics[1].status = TopicStatus.error
    session.commit()

    by_title = {s.title: s for s in docsvc.get_chapter_statuses(session, document.id)}
    cha = by_title["ChA"]
    assert cha.queue_state is QueueLaneState.running
    assert (cha.page_start, cha.page_end) == (12, 79)
    assert cha.topics_total == 2
    assert cha.topics_ready == 1
    assert cha.topics_error == 1
    chb = by_title["ChB"]
    assert chb.queue_state is QueueLaneState.paused
    assert chb.topics_total == 1
    assert chb.topics_queued == 1  # default status, no jobs (paused)


def test_chapter_statuses_scoped_by_document(session: Session) -> None:
    doc1 = _confirm(
        session,
        [ChapterIn(title="D1C", queue_state=QueueLaneState.running, topics=[TopicIn(title="x")])],
    )
    doc2 = _confirm(
        session,
        [ChapterIn(title="D2C", queue_state=QueueLaneState.running, topics=[TopicIn(title="y")])],
    )
    assert [s.title for s in docsvc.get_chapter_statuses(session, doc1.id)] == ["D1C"]
    assert [s.title for s in docsvc.get_chapter_statuses(session, doc2.id)] == ["D2C"]


def test_chapter_statuses_http_shape_and_404(
    client: TestClient, db_factory: sessionmaker
) -> None:
    with db_factory() as db:
        subject = Subject(name="Physics")
        document = Document(subject=subject, filename="f.pdf", file_hash="h")
        db.add_all([subject, document])
        db.commit()
        docsvc.confirm_structure(
            db,
            document.id,
            chapters=[
                ChapterIn(
                    title="Chapter 1",
                    queue_state=QueueLaneState.running,
                    topics=[TopicIn(title="T1")],
                )
            ],
        )
        document_id = document.id

    resp = client.get(f"/api/documents/{document_id}/chapters/status")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    row = body[0]
    assert row["title"] == "Chapter 1"
    assert row["queue_state"] == "running"
    assert {
        "topics_total",
        "topics_ready",
        "topics_processing",
        "topics_queued",
        "topics_error",
    } <= set(row)

    assert client.get("/api/documents/999/chapters/status").status_code == 404


def test_library_summary_counts_running_chapters(session: Session) -> None:
    document = _confirm(
        session,
        [
            ChapterIn(
                title="ChA",
                queue_state=QueueLaneState.running,
                topics=[TopicIn(title="A1")],
            ),
            ChapterIn(
                title="ChB",
                queue_state=QueueLaneState.paused,
                topics=[TopicIn(title="B1")],
            ),
        ],
    )
    summary = next(s for s in docsvc.list_documents(session) if s.id == document.id)
    assert summary.chapters_total == 2
    assert summary.chapters_running == 1


# --- PATCH /api/chapters/{id}/queue_state -----------------------------------


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


def test_patch_chapter_queue_state_resumes_and_404(
    client: TestClient, db_factory: sessionmaker
) -> None:
    with db_factory() as db:
        subject = Subject(name="Physics")
        document = Document(subject=subject, filename="f.pdf", file_hash="h")
        db.add_all([subject, document])
        db.commit()
        docsvc.confirm_structure(
            db,
            document.id,
            chapters=[
                ChapterIn(
                    title="Chapter 1",
                    queue_state=QueueLaneState.paused,
                    topics=[TopicIn(title="T1")],
                )
            ],
        )
        chapter_id = db.scalars(select(Chapter)).one().id
        assert db.scalars(select(QueueJob)).all() == []  # paused → no jobs

    resp = client.patch(
        f"/api/chapters/{chapter_id}/queue_state", json={"queue_state": "running"}
    )
    assert resp.status_code == 204

    with db_factory() as db:
        # Resuming the chapter enqueued its topic.
        assert db.scalars(select(QueueJob)).all() != []
        assert db.get(Chapter, chapter_id).queue_state is QueueLaneState.running

    missing = client.patch(
        "/api/chapters/999/queue_state", json={"queue_state": "running"}
    )
    assert missing.status_code == 404
