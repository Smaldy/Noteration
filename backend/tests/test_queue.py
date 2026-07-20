"""Queue service tests (sub-wave 4a): enqueue, priority/stage ordering, dispatch.

Processing, failover, and resume-from-DB are covered in 4b–4c.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.models import (
    Chapter,
    Document,
    Note,
    ProviderState,
    Subject,
    Topic,
)
from backend.models.enums import (
    QueueLaneState,
    QueueStage,
    QueueState,
    TopicPriority,
    TopicStatus,
)
from backend.models.processing import QueueJob
from backend.services.providers import (
    AllProvidersExhausted,
    MockProvider,
    ProviderResult,
    ProviderUnavailableError,
    Waterfall,
)
from backend.services.queue import QueueService


def _topic(
    session: Session,
    *,
    priority: TopicPriority = TopicPriority.medium,
    order_index: int = 0,
    title: str = "T",
) -> Topic:
    subject = Subject(name="S")
    document = Document(subject=subject, filename="f.pdf", file_hash="h")
    chapter = Chapter(
        document=document,
        subject=subject,
        title="C",
        order_index=0,
        queue_state=QueueLaneState.running,  # chapters default to paused; this lane processes
    )
    topic = Topic(
        chapter=chapter, title=title, priority=priority, order_index=order_index
    )
    session.add(topic)
    session.commit()
    return topic


def test_enqueue_creates_jobs_for_all_stages(session: Session) -> None:
    topic = _topic(session)
    jobs = QueueService(session).enqueue_topic(topic)
    stages = {job.stage for job in jobs}
    # Default stages: formula (region registration) + the consolidated generation
    # stage (`notes`). The separate `assessment` stage is retired.
    assert stages == {QueueStage.formula, QueueStage.notes}
    assert all(job.state is QueueState.pending for job in jobs)


def test_enqueue_skip_priority_creates_nothing(session: Session) -> None:
    topic = _topic(session, priority=TopicPriority.skip)
    assert QueueService(session).enqueue_topic(topic) == []


def test_enqueue_is_idempotent_per_stage(session: Session) -> None:
    topic = _topic(session)
    queue = QueueService(session)
    queue.enqueue_topic(topic, stages=(QueueStage.notes,))
    second = queue.enqueue_topic(topic, stages=(QueueStage.notes, QueueStage.assessment))
    assert {j.stage for j in second} == {QueueStage.assessment}  # notes not duplicated


def test_claim_orders_exam_critical_first(session: Session) -> None:
    queue = QueueService(session)
    medium = _topic(session, priority=TopicPriority.medium, title="med")
    critical = _topic(session, priority=TopicPriority.exam_critical, title="crit")
    queue.enqueue_topic(medium, stages=(QueueStage.notes,))
    queue.enqueue_topic(critical, stages=(QueueStage.notes,))

    claimed = queue.claim_next()
    assert claimed is not None
    assert claimed.topic.title == "crit"
    assert claimed.state is QueueState.running


def test_claim_respects_stage_dependency(session: Session) -> None:
    queue = QueueService(session)
    topic = _topic(session)
    queue.enqueue_topic(topic, stages=(QueueStage.notes, QueueStage.assessment))

    first = queue.claim_next()
    assert first is not None and first.stage is QueueStage.notes  # notes before assessment

    # With notes still running (not done), assessment is not yet eligible.
    assert queue.claim_next() is None

    first.state = QueueState.done
    session.commit()
    second = queue.claim_next()
    assert second is not None and second.stage is QueueStage.assessment


def test_claim_returns_none_when_empty(session: Session) -> None:
    assert QueueService(session).claim_next() is None


@pytest.mark.parametrize(
    ("headroom", "est", "expected"),
    [(100, 10, 10), (95, 10, 9), (5, 10, 0), (100, 0, 0), (10, 3, 3)],
)
def test_budget_count(headroom: int, est: int, expected: int) -> None:
    assert QueueService.budget_count(headroom, est) == expected


# --- 4b: processing -------------------------------------------------------


def _claim(queue: QueueService, topic: Topic, stage: QueueStage) -> QueueJob:
    queue.enqueue_topic(topic, stages=(stage,))
    job = queue.claim_next()
    assert job is not None
    return job


def test_process_success_commits_stamps_and_records_cost(session: Session) -> None:
    queue = QueueService(session)
    topic = _topic(session)
    job = _claim(queue, topic, QueueStage.notes)

    def processor(job: QueueJob, db: Session) -> ProviderResult:
        db.add(Note(topic_id=job.topic_id, content_md="generated"))
        return ProviderResult(
            text="generated", provider="ollama", output_tokens=200, cost=0.5
        )

    queue.process_job(job, processor)

    assert job.state is QueueState.done
    assert job.assigned_provider == "ollama"
    assert session.scalars(select(Note)).one().content_md == "generated"
    state = session.scalars(select(ProviderState)).one()
    assert state.provider == "ollama"
    assert state.total_cost == pytest.approx(0.5)
    assert state.total_tokens == 200


def test_substage_commit_is_independent(session: Session) -> None:
    # Notes commit (and are studiable) before assessment ever runs.
    queue = QueueService(session)
    topic = _topic(session)
    queue.enqueue_topic(topic, stages=(QueueStage.notes, QueueStage.assessment))

    notes_job = queue.claim_next()
    assert notes_job is not None and notes_job.stage is QueueStage.notes
    queue.process_job(
        notes_job,
        lambda j, db: (
            db.add(Note(topic_id=j.topic_id, content_md="n")),
            ProviderResult(text="n", provider="gemini_free"),
        )[1],
    )

    assert notes_job.state is QueueState.done
    assert session.scalars(select(Note)).one() is not None  # committed already
    # assessment is still only pending — its job has not been processed
    assessment = session.scalars(
        select(QueueJob).where(QueueJob.stage == QueueStage.assessment)
    ).one()
    assert assessment.state is QueueState.pending


def test_exhaustion_defers_job_without_consuming_attempt(session: Session) -> None:
    queue = QueueService(session)
    topic = _topic(session)
    job = _claim(queue, topic, QueueStage.notes)
    resume_at = job.created_at  # any datetime works for the assertion

    def processor(job: QueueJob, db: Session) -> ProviderResult:
        db.add(Note(topic_id=job.topic_id, content_md="partial"))  # must be rolled back
        raise AllProvidersExhausted(retry_at=resume_at, reason="429 quota limit:0")

    queue.process_job(job, processor)

    assert job.state is QueueState.pending
    assert job.resume_after == resume_at
    assert job.attempts == 0
    # The reason is recorded so a forever-deferred provider isn't invisible.
    assert job.last_error == "429 quota limit:0"
    assert session.scalars(select(Note)).all() == []  # partial write discarded


def test_failure_rolls_back_partial_write_and_retries(session: Session) -> None:
    queue = QueueService(session, max_attempts=2)
    topic = _topic(session)
    job = _claim(queue, topic, QueueStage.notes)

    def failing(job: QueueJob, db: Session) -> ProviderResult:
        db.add(Note(topic_id=job.topic_id, content_md="half"))
        raise ProviderUnavailableError("boom")

    queue.process_job(job, failing)
    assert job.state is QueueState.pending  # retry
    assert job.attempts == 1
    assert job.last_error == "boom"
    assert session.scalars(select(Note)).all() == []  # nothing half-written

    queue.process_job(job, failing)
    assert job.state is QueueState.failed  # max_attempts reached
    assert job.attempts == 2


# --- topic-status lifecycle (the queue owns Topic.status) -----------------


def _ok(job: QueueJob, db: Session) -> ProviderResult:
    return ProviderResult(text="x", provider="gemini_free")


def test_topic_status_processing_on_claim(session: Session) -> None:
    queue = QueueService(session)
    topic = _topic(session)
    assert topic.status is TopicStatus.queued
    queue.enqueue_topic(topic, stages=(QueueStage.notes,))
    queue.claim_next()
    session.refresh(topic)
    assert topic.status is TopicStatus.processing


def test_topic_status_partial_is_processing(session: Session) -> None:
    queue = QueueService(session)
    topic = _topic(session)
    queue.enqueue_topic(topic, stages=(QueueStage.notes, QueueStage.assessment))
    notes = queue.claim_next()
    assert notes is not None
    queue.process_job(notes, _ok)
    session.refresh(topic)
    # notes done, assessment still pending → partial progress is "processing"
    assert topic.status is TopicStatus.processing


def test_topic_status_ready_when_all_stages_done(session: Session) -> None:
    queue = QueueService(session)
    topic = _topic(session)
    queue.enqueue_topic(topic, stages=(QueueStage.notes, QueueStage.assessment))
    for _ in range(2):
        job = queue.claim_next()
        assert job is not None
        queue.process_job(job, _ok)
    session.refresh(topic)
    assert topic.status is TopicStatus.ready


def test_topic_status_error_on_terminal_failure(session: Session) -> None:
    queue = QueueService(session, max_attempts=1)
    topic = _topic(session)
    job = _claim(queue, topic, QueueStage.notes)
    queue.process_job(
        job,
        lambda j, db: (_ for _ in ()).throw(ProviderUnavailableError("boom")),
    )
    session.refresh(topic)
    assert topic.status is TopicStatus.error


def test_topic_status_sync_without_autoflush() -> None:
    """Production SessionLocal uses autoflush=False; the status sync must see the
    job states it just set without relying on the test session's autoflush."""
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
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    try:
        topic = _topic(db)
        queue = QueueService(db)
        job = _claim(queue, topic, QueueStage.notes)
        queue.process_job(job, _ok)
        db.refresh(topic)
        assert topic.status is TopicStatus.ready
    finally:
        db.close()
        engine.dispose()


def test_process_through_waterfall(session: Session) -> None:
    # Integration: the stage processor calls the waterfall, which fails over.
    queue = QueueService(session)
    topic = _topic(session)
    job = _claim(queue, topic, QueueStage.notes)

    waterfall = Waterfall(
        [
            MockProvider("gemini_free", available=False, reset_at=job.created_at),
            MockProvider("ollama", text="notes!", cost=0.1),
        ]
    )

    def processor(job: QueueJob, db: Session) -> ProviderResult:
        result = waterfall.generate("prompt", max_tokens=500)
        db.add(Note(topic_id=job.topic_id, content_md=result.text))
        return result

    queue.process_job(job, processor)

    assert job.state is QueueState.done
    assert job.assigned_provider == "ollama"  # failed over from gemini
    assert session.scalars(select(Note)).one().content_md == "notes!"


# --- 4c: resume-from-DB + restart proof -----------------------------------


def test_recover_orphaned_running_jobs(session: Session) -> None:
    queue = QueueService(session)
    topic = _topic(session)
    job = _claim(queue, topic, QueueStage.notes)  # left in `running`
    assert job.state is QueueState.running

    recovered = QueueService(session).recover_orphaned_jobs()
    assert recovered == 1
    assert job.state is QueueState.pending


def test_earliest_resume_after(session: Session) -> None:
    queue = QueueService(session)
    assert queue.earliest_resume_after() is None

    sooner = datetime(2026, 6, 1, tzinfo=UTC)
    later = datetime(2026, 6, 2, tzinfo=UTC)
    for resume_at in (later, sooner):
        topic = _topic(session)
        job = _claim(queue, topic, QueueStage.notes)
        queue.process_job(
            job, lambda j, db, r=resume_at: _raise(AllProvidersExhausted(retry_at=r))
        )

    assert queue.earliest_resume_after() == sooner


def test_mid_job_limit_then_restart_completes_all(session: Session) -> None:
    """The reliability proof: a limit hit mid-batch loses no work, writes nothing
    half, survives a restart, and resumes to completion."""
    queue = QueueService(session)
    for i in range(3):
        topic = _topic(
            session, priority=TopicPriority.exam_critical, order_index=i, title=f"t{i}"
        )
        queue.enqueue_topic(topic, stages=(QueueStage.notes,))

    resume_at = datetime(2026, 6, 1, tzinfo=UTC)
    calls = {"n": 0}

    def limited(job: QueueJob, db: Session) -> ProviderResult:
        calls["n"] += 1
        if calls["n"] == 1:  # first topic succeeds before the window closes
            db.add(Note(topic_id=job.topic_id, content_md="committed"))
            return ProviderResult(text="committed", provider="gemini_free")
        db.add(Note(topic_id=job.topic_id, content_md="PARTIAL"))  # must roll back
        raise AllProvidersExhausted(retry_at=resume_at)

    # Run 1: one topic commits, then the window is exhausted.
    queue.run_batch(limited, max_jobs=10)
    done = session.scalars(select(QueueJob).where(QueueJob.state == QueueState.done)).all()
    assert len(done) == 1
    notes = session.scalars(select(Note)).all()
    assert [n.content_md for n in notes] == ["committed"]  # partial write discarded
    assert queue.earliest_resume_after() == resume_at

    # Simulate a crash mid-process on another job.
    pending = session.scalars(
        select(QueueJob).where(QueueJob.state == QueueState.pending)
    ).all()
    assert len(pending) == 2
    pending[0].state = QueueState.running
    session.commit()

    # Restart: a fresh process/session reading only from the DB, woken at the
    # reset time (its clock now reports `resume_at`, so deferred jobs are due).
    fresh = Session(bind=session.get_bind())
    restarted = QueueService(fresh, clock=lambda: resume_at)
    assert restarted.recover_orphaned_jobs() == 1
    assert restarted.earliest_resume_after() == resume_at

    # Resume: window reopened, provider healthy.
    def healthy(job: QueueJob, db: Session) -> ProviderResult:
        db.add(Note(topic_id=job.topic_id, content_md=f"resumed-{job.topic_id}"))
        return ProviderResult(text="ok", provider="gemini_free")

    restarted.run_batch(healthy, max_jobs=10)

    all_jobs = fresh.scalars(select(QueueJob)).all()
    assert len(all_jobs) == 3
    assert all(j.state is QueueState.done for j in all_jobs)  # no work lost
    assert len(fresh.scalars(select(Note)).all()) == 3  # exactly one per topic
    fresh.close()


def test_claim_skips_jobs_deferred_into_the_future(session: Session) -> None:
    # A job deferred past `now` must not be claimed (don't hit a cooling provider).
    now = datetime(2026, 1, 1, tzinfo=UTC)
    queue = QueueService(session, clock=lambda: now)
    topic = _topic(session)
    job = _claim(queue, topic, QueueStage.notes)
    queue.process_job(
        job,
        lambda j, db: _raise(AllProvidersExhausted(retry_at=now + timedelta(hours=1))),
    )
    assert job.state is QueueState.pending
    assert queue.claim_next() is None  # deferred — not due yet


def test_run_batch_continues_past_a_failing_topic(session: Session) -> None:
    # A transiently failing topic is deferred, not allowed to block other topics.
    now = datetime(2026, 1, 1, tzinfo=UTC)
    queue = QueueService(session, clock=lambda: now)
    bad = _topic(session, order_index=0, title="bad")
    good = _topic(session, order_index=1, title="good")
    queue.enqueue_topic(bad, stages=(QueueStage.notes,))
    queue.enqueue_topic(good, stages=(QueueStage.notes,))

    def processor(job: QueueJob, db: Session) -> ProviderResult:
        if job.topic.title == "bad":
            raise ProviderUnavailableError("boom")
        db.add(Note(topic_id=job.topic_id, content_md="good notes"))
        return ProviderResult(text="ok", provider="gemini_free")

    processed = queue.run_batch(processor, max_jobs=10)

    assert processed == 2  # both attempted; bad deferred, good done
    assert session.scalars(select(Note)).one().content_md == "good notes"


def _raise(exc: Exception) -> ProviderResult:
    raise exc


# --- per-document token budget (cost guard, defense-in-depth) ----------------


def test_estimate_topic_tokens() -> None:
    from backend.services.queue import EST_TOKENS_PER_TOPIC, estimate_topic_tokens

    assert estimate_topic_tokens(0) == 0
    assert estimate_topic_tokens(3) == 3 * EST_TOKENS_PER_TOPIC


def test_process_records_tokens_used(session: Session) -> None:
    queue = QueueService(session)
    topic = _topic(session)
    job = _claim(queue, topic, QueueStage.notes)

    queue.process_job(
        job,
        lambda j, db: ProviderResult(
            text="n", provider="gemini_free", input_tokens=1200, output_tokens=800
        ),
    )

    assert job.state is QueueState.done
    assert job.tokens_used == 2000  # input + output recorded for the budget guard


def test_auto_budget_pauses_runaway_document(session: Session) -> None:
    # One non-skip topic → auto ceiling = EST_TOKENS_PER_TOPIC * factor.
    topic = _topic(session)
    queue = QueueService(session)  # per_doc_token_budget=0 → automatic
    queue.enqueue_topic(topic, stages=(QueueStage.notes, QueueStage.assessment))

    notes = queue.claim_next()
    assert notes is not None and notes.stage is QueueStage.notes
    # Notes alone blows way past the auto ceiling.
    queue.process_job(
        notes,
        lambda j, db: ProviderResult(
            text="x", provider="gemini_free", input_tokens=60_000
        ),
    )
    assert notes.tokens_used == 60_000

    # Assessment's prerequisites are done, but the document is over budget, so it
    # is not claimed (paused) — it stays pending, not failed.
    assert queue.claim_next() is None
    assessment = session.scalars(
        select(QueueJob).where(QueueJob.stage == QueueStage.assessment)
    ).one()
    assert assessment.state is QueueState.pending

    # Raising the ceiling (flat override) makes the paused job claimable again.
    generous = QueueService(session, per_doc_token_budget=1_000_000)
    resumed = generous.claim_next()
    assert resumed is not None and resumed.stage is QueueStage.assessment


def test_flat_budget_override_blocks_below_auto(session: Session) -> None:
    topic = _topic(session)
    queue = QueueService(session, per_doc_token_budget=1000)  # tiny flat ceiling
    queue.enqueue_topic(topic, stages=(QueueStage.notes, QueueStage.assessment))

    notes = queue.claim_next()
    assert notes is not None
    queue.process_job(
        notes,
        lambda j, db: ProviderResult(
            text="x", provider="gemini_free", output_tokens=1500
        ),
    )
    # Spent 1500 ≥ 1000 ceiling → the rest of the document is paused.
    assert queue.claim_next() is None
