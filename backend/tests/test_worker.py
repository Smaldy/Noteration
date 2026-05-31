"""Background worker tests (queue driver).

Covers the gap that left "added my key, nothing happened": the queue is pure and
something must drive it. These prove the gating (no work / no provider → no-op,
jobs untouched) and that the background thread actually drains a confirmed
document end-to-end through the real pipeline.
"""

from __future__ import annotations

import json
import time
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base
from backend.models import Document, Note, Subject
from backend.models.enums import QueueState, TopicPriority, TopicStatus
from backend.models.hierarchy import Topic
from backend.models.processing import QueueJob
from backend.models.settings import Settings
from backend.schemas.structure import ChapterIn, TopicIn
from backend.services import documents as docsvc
from backend.services import worker as worker_mod
from backend.services.providers.base import BudgetProbe, Provider, ProviderResult
from backend.services.providers.waterfall import Waterfall
from backend.services.queue import QueueService
from backend.services.worker import QueueWorker, _has_configured_provider, drain_once


class _SmartProvider(Provider):
    """Answers assessment prompts with JSON, everything else with notes prose."""

    name = "mock_free"
    supports_vision = True

    def generate(self, prompt: str, *, max_tokens: int) -> ProviderResult:
        if "Respond with ONLY a JSON" in prompt:
            payload = {
                "mcqs": [
                    {
                        "question": "v?",
                        "options": ["dx/dt", "ma"],
                        "correct_index": 0,
                        "explanation": "rate",
                    }
                ],
                "flashcards": [{"front": "a?", "back": "dv/dt"}],
            }
            return ProviderResult(text=json.dumps(payload), provider=self.name)
        return ProviderResult(text="# Kinematics\n\nVelocity is dx/dt.", provider=self.name)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        return ProviderResult(text="v = dx/dt", provider=self.name)

    def budget_probe(self) -> BudgetProbe:
        return BudgetProbe(True, 100, "none", None, True)


# --- gating units (no thread) ------------------------------------------------


def test_has_configured_provider_truth_table() -> None:
    assert _has_configured_provider(Settings(api_key_gemini="k")) is True
    assert _has_configured_provider(
        Settings(allow_paid=True, api_key_claude="k")
    ) is True
    # Claude key without allow_paid is the hard never-spend case → not usable.
    assert _has_configured_provider(Settings(api_key_claude="k")) is False
    assert _has_configured_provider(Settings()) is False


def test_drain_once_noop_when_no_pending_jobs(session: Session) -> None:
    assert drain_once(session) == 0


def test_drain_once_leaves_jobs_pending_when_unconfigured(
    session: Session, tmp_path: Path
) -> None:
    _seed_confirmed_document(session, tmp_path)
    # No Settings row / no key → gate fails; jobs must stay claimable (no defer).
    processed = drain_once(session)
    assert processed == 0
    jobs = session.query(QueueJob).all()
    assert jobs and all(j.state is QueueState.pending for j in jobs)
    assert all(j.resume_after is None for j in jobs)


# --- background-thread integration -------------------------------------------


@pytest.fixture
def db_factory() -> Generator[sessionmaker, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared in-memory connection across threads
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record) -> None:  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


def _seed_confirmed_document(session: Session, tmp_path: Path) -> Document:
    md = tmp_path / "doc.md"
    md.write_text("# Kinematics\n\nVelocity is dx/dt.\n", encoding="utf-8")
    subject = Subject(name="Physics")
    document = Document(
        subject=subject, filename="f.pdf", file_hash="h", markdown_path=str(md)
    )
    session.add_all([subject, document])
    session.commit()
    docsvc.confirm_structure(
        session,
        document.id,
        chapters=[
            ChapterIn(
                title="Mechanics",
                topics=[TopicIn(title="Kinematics", priority=TopicPriority.exam_critical)],
            )
        ],
    )
    return document


def test_worker_thread_drains_confirmed_document(
    db_factory: sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Seed a confirmed document (enqueues its topic's stages) and a usable key.
    seed = db_factory()
    _seed_confirmed_document(seed, tmp_path)
    seed.add(Settings(id=1, api_key_gemini="x"))
    seed.commit()
    topic_id = seed.query(QueueJob).first().topic_id
    seed.close()

    # Swap the real network waterfall for the in-memory smart provider.
    monkeypatch.setattr(
        worker_mod,
        "build_waterfall_from_settings",
        lambda settings, **kw: Waterfall([_SmartProvider()]),
    )

    worker = QueueWorker(db_factory, poll_interval=0.02)
    worker.start()
    try:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            check = db_factory()
            done = check.query(QueueJob).filter_by(state=QueueState.done).count()
            total = check.query(QueueJob).count()
            check.close()
            if total and done == total:
                break
            time.sleep(0.05)
    finally:
        worker.stop()

    verify = db_factory()
    jobs = verify.query(QueueJob).all()
    assert jobs and all(j.state is QueueState.done for j in jobs)
    topic = verify.get(Topic, topic_id)
    assert topic.status is TopicStatus.ready
    assert verify.query(Note).filter_by(topic_id=topic_id).count() == 1
    verify.close()
