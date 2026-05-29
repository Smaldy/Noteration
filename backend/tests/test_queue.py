"""Queue service tests (sub-wave 4a): enqueue, priority/stage ordering, dispatch.

Processing, failover, and resume-from-DB are covered in 4b–4c.
"""

import pytest
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import QueueStage, QueueState, TopicPriority
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
