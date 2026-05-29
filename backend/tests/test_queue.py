"""Queue service tests (sub-wave 4a): enqueue, priority/stage ordering, dispatch.

Processing, failover, and resume-from-DB are covered in 4b–4c.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    Chapter,
    Document,
    Note,
    ProviderState,
    Subject,
    Topic,
)
from backend.models.enums import QueueStage, QueueState, TopicPriority
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
    chapter = Chapter(document=document, subject=subject, title="C", order_index=0)
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
    assert stages == {QueueStage.formula, QueueStage.notes, QueueStage.assessment}
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
            text="generated", provider="claude_paid", output_tokens=200, cost=0.5
        )

    queue.process_job(job, processor)

    assert job.state is QueueState.done
    assert job.assigned_provider == "claude_paid"
    assert session.scalars(select(Note)).one().content_md == "generated"
    state = session.scalars(select(ProviderState)).one()
    assert state.provider == "claude_paid"
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
        raise AllProvidersExhausted(retry_at=resume_at)

    queue.process_job(job, processor)

    assert job.state is QueueState.pending
    assert job.resume_after == resume_at
    assert job.attempts == 0
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


def test_process_through_waterfall(session: Session) -> None:
    # Integration: the stage processor calls the waterfall, which fails over.
    queue = QueueService(session)
    topic = _topic(session)
    job = _claim(queue, topic, QueueStage.notes)

    waterfall = Waterfall(
        [
            MockProvider("gemini_free", available=False, reset_at=job.created_at),
            MockProvider("claude_paid", text="notes!", cost=0.1),
        ]
    )

    def processor(job: QueueJob, db: Session) -> ProviderResult:
        result = waterfall.generate("prompt", max_tokens=500)
        db.add(Note(topic_id=job.topic_id, content_md=result.text))
        return result

    queue.process_job(job, processor)

    assert job.state is QueueState.done
    assert job.assigned_provider == "claude_paid"  # failed over from gemini
    assert session.scalars(select(Note)).one().content_md == "notes!"
