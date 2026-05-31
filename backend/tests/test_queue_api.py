"""Queue view + retry tests (Phase 9e): status counts, errors, retry."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app
from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import (
    QueueStage,
    QueueState,
    TopicPriority,
    TopicStatus,
)
from backend.models.processing import QueueJob
from backend.services import queue_view
from backend.services.queue import QueueService


def _seed(db: Session) -> int:
    """One document with topics across all statuses + a failed job. Returns doc id.

    A second document with its own ready topic verifies document scoping.
    """
    subject = Subject(name="Physics")
    db.add(subject)
    db.flush()
    doc = Document(subject_id=subject.id, filename="a.pdf", file_hash="h1")
    other = Document(subject_id=subject.id, filename="b.pdf", file_hash="h2")
    db.add_all([doc, other])
    db.flush()
    ch = Chapter(document_id=doc.id, subject_id=subject.id, title="C", order_index=0)
    ch2 = Chapter(document_id=other.id, subject_id=subject.id, title="C2", order_index=0)
    db.add_all([ch, ch2])
    db.flush()

    db.add_all(
        [
            Topic(chapter_id=ch.id, title="ready", status=TopicStatus.ready),
            Topic(chapter_id=ch.id, title="processing", status=TopicStatus.processing),
            Topic(chapter_id=ch.id, title="queued", status=TopicStatus.queued),
            # skip topics are excluded from queue counts
            Topic(
                chapter_id=ch.id,
                title="skipped",
                status=TopicStatus.queued,
                priority=TopicPriority.skip,
            ),
            Topic(chapter_id=ch2.id, title="other-ready", status=TopicStatus.ready),
        ]
    )
    db.flush()
    errored = Topic(chapter_id=ch.id, title="errored", status=TopicStatus.error)
    db.add(errored)
    db.flush()
    db.add(
        QueueJob(
            topic_id=errored.id,
            stage=QueueStage.notes,
            state=QueueState.failed,
            last_error="provider exploded",
        )
    )
    db.commit()
    return doc.id


# --- service unit tests ------------------------------------------------------


def test_status_counts_exclude_skip_and_scope_by_document(session: Session) -> None:
    doc_id = _seed(session)
    status = queue_view.get_queue_status(session, document_id=doc_id)

    assert (status.ready, status.processing, status.queued, status.error) == (
        1,
        1,
        1,
        1,
    )
    assert status.total == 4  # skip excluded; other-doc topic excluded
    assert len(status.errors) == 1
    assert status.errors[0].title == "errored"
    assert status.errors[0].last_error == "provider exploded"


def test_status_global_counts_all_documents(session: Session) -> None:
    _seed(session)
    status = queue_view.get_queue_status(session)
    assert status.ready == 2  # both documents' ready topics
    assert status.total == 5


def test_status_surfaces_paused_reason_for_deferred_work(session: Session) -> None:
    """A job deferred on exhaustion exposes its recorded reason (not just a time)."""
    doc_id = _seed(session)
    queued = session.scalars(select(Topic).where(Topic.title == "queued")).one()
    resume_at = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    session.add(
        QueueJob(
            topic_id=queued.id,
            stage=QueueStage.notes,
            state=QueueState.pending,
            resume_after=resume_at,
            last_error="gemini_free: 429 quota limit:0",
        )
    )
    session.commit()

    status = queue_view.get_queue_status(session, document_id=doc_id)
    assert status.resume_at == resume_at
    assert status.paused_reason == "gemini_free: 429 quota limit:0"


def test_status_flags_budget_paused_document(session: Session) -> None:
    doc_id = _seed(session)
    # The document already spent past a tiny flat ceiling, and it still has
    # unfinished topics (queued/processing) → it should report as budget-paused.
    queued = session.scalars(select(Topic).where(Topic.title == "queued")).one()
    session.add(
        QueueJob(
            topic_id=queued.id,
            stage=QueueStage.notes,
            state=QueueState.done,
            tokens_used=5000,
        )
    )
    session.commit()

    status = queue_view.get_queue_status(
        session, document_id=doc_id, per_doc_token_budget=1000
    )
    assert status.token_spent >= 5000
    assert status.token_budget == 1000
    assert status.budget_paused is True

    # A generous ceiling above spend → not paused.
    relaxed = queue_view.get_queue_status(
        session, document_id=doc_id, per_doc_token_budget=1_000_000
    )
    assert relaxed.budget_paused is False


def test_retry_topic_requeues_failed_jobs(session: Session) -> None:
    _seed(session)
    errored = session.scalars(
        select(Topic).where(Topic.title == "errored")
    ).one()

    retried = QueueService(session).retry_topic(errored.id)
    assert retried == 1

    job = session.scalars(
        select(QueueJob).where(QueueJob.topic_id == errored.id)
    ).one()
    assert job.state is QueueState.pending
    assert job.attempts == 0
    assert job.last_error is None
    session.refresh(errored)
    assert errored.status is TopicStatus.queued  # back in the queue


# --- HTTP tests (shared in-memory DB via StaticPool) ------------------------


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


def test_http_queue_status(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        doc_id = _seed(db)

    response = client.get(f"/api/queue/status?document_id={doc_id}")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["error"] == 1
    assert body["total"] == 4
    assert body["errors"][0]["last_error"] == "provider exploded"


def test_http_retry(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        _seed(db)
        topic_id = db.scalars(select(Topic).where(Topic.title == "errored")).one().id

    response = client.post(f"/api/queue/topics/{topic_id}/retry")
    assert response.status_code == 200, response.text
    assert response.json() == {"topic_id": topic_id, "retried_jobs": 1}


def test_http_retry_unknown_topic_404(client: TestClient) -> None:
    assert client.post("/api/queue/topics/999/retry").status_code == 404
