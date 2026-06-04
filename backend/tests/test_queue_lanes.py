"""Per-subject queue lane tests (Wave B, reliability core).

Locks the lane arbitration contract: one in-flight topic per provider, distinct
providers run concurrently, foreground lanes win provider contention, paused lanes
hand their provider to a waiting lane and survive restart, and overnight is
per-subject with exam_critical-first ordering inside each lane.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import (
    QueueLaneState,
    QueueStage,
    QueueState,
    TopicPriority,
    TopicStatus,
)
from backend.models.processing import QueueJob
from backend.services.providers.base import BudgetProbe, Provider, ProviderResult
from backend.services.queue import QueueService, SubjectLaneNotFound


class _FakeProvider(Provider):
    """A minimal provider for arbitration: name + availability, no real calls."""

    def __init__(
        self, name: str, *, available: bool = True, headroom: int = 100, enabled: bool = True
    ) -> None:
        self.name = name
        self.enabled = enabled
        self._available = available
        self._headroom = headroom

    def generate(self, prompt, *, max_tokens, response_schema=None) -> ProviderResult:
        return ProviderResult(text="x", provider=self.name)

    def transcribe_image(self, image, *, max_tokens=1024) -> ProviderResult:  # pragma: no cover
        return ProviderResult(text="x", provider=self.name)

    def budget_probe(self) -> BudgetProbe:
        axis = "none" if self._available else "rpm"
        return BudgetProbe(self._available, self._headroom, axis, None, False)


def _lane(
    session: Session,
    name: str,
    titles: list[str],
    *,
    state: QueueLaneState = QueueLaneState.running,
    priorities: dict[str, TopicPriority] | None = None,
    stages: tuple[QueueStage, ...] = (QueueStage.notes,),
) -> tuple[Subject, list[Topic]]:
    """Seed a subject lane with topics and enqueue their jobs."""
    subject = Subject(name=name, queue_state=state)
    doc = Document(subject=subject, filename="f.pdf", file_hash=name)
    chapter = Chapter(document=doc, subject=subject, title="Ch", order_index=0)
    topics = [
        Topic(
            chapter=chapter,
            title=t,
            order_index=i,
            priority=(priorities or {}).get(t, TopicPriority.medium),
        )
        for i, t in enumerate(titles)
    ]
    session.add_all([subject, doc, chapter, *topics])
    session.commit()
    queue = QueueService(session)
    for topic in topics:
        queue.enqueue_topic(topic, stages=stages)
    return subject, topics


# --- one in-flight per provider (point 7) -----------------------------------


def test_single_lane_single_provider_claims_one_then_blocks(session: Session) -> None:
    _lane(session, "Physics", ["A", "B"])
    queue = QueueService(session)
    gemini = _FakeProvider("gemini_free")

    first = queue.claim_dispatch([gemini])
    assert len(first) == 1  # only one topic in-flight on the single provider

    # The provider now holds a running job → no second claim until it finishes.
    assert queue.claim_dispatch([gemini]) == []


def test_single_lane_uses_only_one_provider_at_a_time(session: Session) -> None:
    # A lane can't split a topic across two providers — one in-flight topic total.
    _lane(session, "Physics", ["A", "B"])
    queue = QueueService(session)
    claims = queue.claim_dispatch([_FakeProvider("gemini_free"), _FakeProvider("ollama")])
    assert len(claims) == 1


def test_distinct_providers_run_two_lanes_concurrently(session: Session) -> None:
    a, _ = _lane(session, "Physics", ["A"])
    b, _ = _lane(session, "Chemistry", ["B"])
    queue = QueueService(session)
    claims = queue.claim_dispatch([_FakeProvider("gemini_free"), _FakeProvider("ollama")])

    assert len(claims) == 2
    assert {c.provider for c in claims} == {"gemini_free", "ollama"}
    claimed_subjects = {
        session.get(QueueJob, c.job_id).subject_id for c in claims
    }
    assert claimed_subjects == {a.id, b.id}


def test_unavailable_provider_is_not_assigned(session: Session) -> None:
    _lane(session, "Physics", ["A"])
    queue = QueueService(session)
    # Provider has no headroom → no claim, work stays pending.
    assert queue.claim_dispatch([_FakeProvider("gemini_free", available=False)]) == []


# --- provider contention: foreground wins (point 8) -------------------------


def test_foreground_lane_wins_contention_over_overnight(session: Session) -> None:
    fg, _ = _lane(session, "Physics", ["A"], state=QueueLaneState.running)
    bg, _ = _lane(session, "Chemistry", ["B"], state=QueueLaneState.overnight)
    queue = QueueService(session)
    gemini = _FakeProvider("gemini_free")

    claims = queue.claim_dispatch([gemini])
    assert len(claims) == 1
    assert session.get(QueueJob, claims[0].job_id).subject_id == fg.id  # foreground won

    # The background lane is waiting on the contended provider.
    assert queue.waiting_lanes([gemini]) == {bg.id: "gemini_free"}


def test_no_waiting_when_no_contention(session: Session) -> None:
    _lane(session, "Physics", ["A"])
    queue = QueueService(session)
    gemini = _FakeProvider("gemini_free")
    queue.claim_dispatch([gemini])  # the only lane is now in-flight
    assert queue.waiting_lanes([gemini]) == {}


# --- pause / resume + manual hand-over (point 9) ----------------------------


def test_pause_hands_single_provider_to_waiting_lane(session: Session) -> None:
    a, _ = _lane(session, "Physics", ["A"], state=QueueLaneState.overnight)
    b, _ = _lane(session, "Chemistry", ["B"], state=QueueLaneState.overnight)
    queue = QueueService(session)
    ollama = _FakeProvider("ollama")

    first = queue.claim_dispatch([ollama])
    assert len(first) == 1
    holder = session.get(QueueJob, first[0].job_id).subject_id
    waiter = b.id if holder == a.id else a.id

    # Ollama is in-flight for the holder; the waiter can't claim it.
    assert queue.claim_dispatch([ollama]) == []

    # Pause the holder → its in-flight job rolls back and frees Ollama.
    queue.pause_lane(holder)
    held_job = session.get(QueueJob, first[0].job_id)
    assert held_job.state is QueueState.pending
    assert held_job.assigned_provider is None

    second = queue.claim_dispatch([ollama])
    assert len(second) == 1
    assert session.get(QueueJob, second[0].job_id).subject_id == waiter  # hand-over


def test_paused_lane_does_not_dispatch_and_resume_restores(session: Session) -> None:
    subject, _ = _lane(session, "Physics", ["A"], state=QueueLaneState.paused)
    queue = QueueService(session)
    gemini = _FakeProvider("gemini_free")

    assert queue.claim_dispatch([gemini]) == []  # paused → no dispatch

    queue.resume_lane(subject.id)
    assert subject.queue_state is QueueLaneState.running
    assert len(queue.claim_dispatch([gemini])) == 1


def test_pause_unknown_subject_raises(session: Session) -> None:
    with pytest.raises(SubjectLaneNotFound):
        QueueService(session).pause_lane(999)


def test_pause_survives_restart_with_no_half_written_work(session: Session) -> None:
    subject, topics = _lane(session, "Physics", ["A"])
    queue = QueueService(session)
    gemini = _FakeProvider("gemini_free")

    claim = queue.claim_dispatch([gemini])[0]
    assert session.get(QueueJob, claim.job_id).state is QueueState.running

    # Pause mid-flight: clean rollback to queued, no domain rows written.
    queue.pause_lane(subject.id)

    # Simulate an app restart: a fresh service recovers orphaned (running) jobs.
    restarted = QueueService(session)
    assert restarted.recover_orphaned_jobs() == 0  # pause already rolled it back

    session.expire_all()
    subject = session.get(Subject, subject.id)
    job = session.get(QueueJob, claim.job_id)
    assert subject.queue_state is QueueLaneState.paused  # persisted across "restart"
    assert job.state is QueueState.pending and job.resume_after is None
    assert session.get(Topic, topics[0].id).status is TopicStatus.queued
    # Resume → the lane dispatches again from where it left off.
    restarted.resume_lane(subject.id)
    assert len(restarted.claim_dispatch([gemini])) == 1


# --- overnight is per-subject, exam_critical first (point 10) ----------------


def test_overnight_lane_dispatches_exam_critical_first(session: Session) -> None:
    _lane(
        session,
        "Physics",
        ["medium-topic", "critical-topic"],
        state=QueueLaneState.overnight,
        priorities={"critical-topic": TopicPriority.exam_critical},
    )
    queue = QueueService(session)
    claim = queue.claim_dispatch([_FakeProvider("gemini_free")])[0]
    topic = session.get(QueueJob, claim.job_id).topic
    assert topic.priority is TopicPriority.exam_critical  # critical-first within lane


def test_release_running_job_frees_a_stranded_claim(session: Session) -> None:
    subject, _ = _lane(session, "Physics", ["A"])
    queue = QueueService(session)
    claim = queue.claim_dispatch([_FakeProvider("gemini_free")])[0]
    job = session.get(QueueJob, claim.job_id)
    assert job.state is QueueState.running

    # A worker that died mid-claim leaves the job running; releasing frees it.
    assert queue.release_running_job(claim.job_id) is True
    session.expire(job)
    assert job.state is QueueState.pending and job.assigned_provider is None
    # Idempotent: a job that isn't running is left alone.
    assert queue.release_running_job(claim.job_id) is False


def test_multiple_subjects_overnight_independently(session: Session) -> None:
    a, _ = _lane(session, "Physics", ["A"], state=QueueLaneState.overnight)
    b, _ = _lane(session, "Chemistry", ["B"], state=QueueLaneState.overnight)
    queue = QueueService(session)
    claims = queue.claim_dispatch([_FakeProvider("gemini_free"), _FakeProvider("ollama")])
    # Both overnight lanes dispatch at once on distinct providers.
    assert {session.get(QueueJob, c.job_id).subject_id for c in claims} == {a.id, b.id}
