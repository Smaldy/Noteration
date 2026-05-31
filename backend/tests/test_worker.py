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
from datetime import datetime, timezone
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
from backend.services.providers.budget import FreeTierLimiter
from backend.services.providers.waterfall import Waterfall
from backend.services.worker import (
    QueueWorker,
    WaterfallCache,
    _has_configured_provider,
    drain_once,
)
from backend.services.queue import QueueService


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


# --- rate-limit persistence across ticks (429 regression) --------------------


class _LimitedSmartProvider(_SmartProvider):
    """A smart provider with a real per-minute limiter that counts calls.

    Stands in for Gemini's free tier: a low rpm and a frozen clock so its budget
    window can't reopen between drains. If the worker rebuilt the waterfall every
    tick, this provider's call count would exceed ``rpm`` (the live 429 bug).
    """

    name = "gemini_free"

    def __init__(self, *, rpm: int, clock) -> None:
        self.limiter = FreeTierLimiter(rpm=rpm, rpd=10**6)
        self.clock = clock
        self.calls = 0

    def generate(self, prompt: str, *, max_tokens: int) -> ProviderResult:
        self.calls += 1
        self.limiter.record(self.clock())
        return super().generate(prompt, max_tokens=max_tokens)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        self.calls += 1
        self.limiter.record(self.clock())
        return super().transcribe_image(image, max_tokens=max_tokens)

    def budget_probe(self) -> BudgetProbe:
        snap = self.limiter.snapshot(self.clock())
        return BudgetProbe(
            snap.available, snap.headroom, snap.binding_axis, snap.reset_at, True
        )


def _seed_two_topic_document(session: Session, tmp_path: Path) -> None:
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
                topics=[
                    TopicIn(title="Kinematics", priority=TopicPriority.exam_critical),
                    TopicIn(title="Dynamics", priority=TopicPriority.exam_critical),
                ],
            )
        ],
    )


def test_waterfall_cache_rebuilds_only_on_settings_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builds: list[Settings] = []
    monkeypatch.setattr(
        worker_mod,
        "build_waterfall_from_settings",
        lambda settings, **kw: builds.append(settings) or Waterfall([_SmartProvider()]),
    )
    cache = WaterfallCache()

    settings = Settings(id=1, api_key_gemini="k")
    first = cache.for_settings(settings)
    second = cache.for_settings(settings)
    assert first is second  # reused — limiter state survives
    assert len(builds) == 1

    settings.api_key_gemini = "different"  # user saved a new key
    third = cache.for_settings(settings)
    assert third is not first  # rebuilt so the change takes effect
    assert len(builds) == 2

    settings.gemini_model = "gemini-2.5-flash"  # user picked a different model
    fourth = cache.for_settings(settings)
    assert fourth is not third  # rebuilt so the new model takes effect
    assert len(builds) == 3


def test_drain_reuses_waterfall_so_rate_limit_persists(
    session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed_two_topic_document(session, tmp_path)
    session.add(Settings(id=1, api_key_gemini="x"))
    session.commit()

    frozen = datetime(2026, 5, 31, 12, 0, 0, tzinfo=timezone.utc)
    clock = lambda: frozen  # noqa: E731 - window can't reopen between drains
    built: list[_LimitedSmartProvider] = []

    def fake_build(settings, **kw):
        provider = _LimitedSmartProvider(rpm=2, clock=clock)
        built.append(provider)
        return Waterfall([provider], clock=clock)

    monkeypatch.setattr(worker_mod, "build_waterfall_from_settings", fake_build)

    cache = WaterfallCache()
    drain_once(session, cache=cache, clock=clock)
    drain_once(session, cache=cache, clock=clock)

    # The waterfall is built once and reused, so its limiter keeps the first
    # tick's history: total calls stay capped at rpm even though more jobs are
    # pending. (The pre-fix code rebuilt each tick → fresh limiter → 429 burst.)
    assert len(built) == 1
    assert built[0].calls == 2
    # Proof there was leftover work the persisted limiter actually held back.
    assert session.query(QueueJob).filter_by(state=QueueState.done).count() < (
        session.query(QueueJob).count()
    )
