"""Lane status + history API tests (Wave C).

Covers the generation-history log (topic-generated + provider-switch events), the
lane-aware status read model (pause/resume + failover reflected), and the lane
control + history HTTP endpoints.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import HistoryEventType, QueueStage, QueueState
from backend.models.processing import QueueJob
from backend.services import history, queue_view
from backend.services.providers.base import BudgetProbe, Provider, ProviderResult
from backend.services.queue import QueueService

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


class _FP(Provider):
    def __init__(self, name: str, *, enabled: bool = True, available: bool = True) -> None:
        self.name = name
        self.enabled = enabled
        self._available = available

    def generate(self, prompt, *, max_tokens, response_schema=None) -> ProviderResult:
        return ProviderResult(text="x", provider=self.name)

    def transcribe_image(self, image, *, max_tokens=1024) -> ProviderResult:  # pragma: no cover
        return ProviderResult(text="x", provider=self.name)

    def budget_probe(self) -> BudgetProbe:
        return BudgetProbe(self._available, 100, "none", None, False)


def _seed_lane(db: Session, name: str, n_topics: int = 1) -> Subject:
    subject = Subject(name=name)
    doc = Document(subject=subject, filename="f.pdf", file_hash=name)
    chapter = Chapter(document=doc, subject=subject, title="Ch", order_index=0)
    topics = [Topic(chapter=chapter, title=f"{name}-{i}", order_index=i) for i in range(n_topics)]
    db.add_all([subject, doc, chapter, *topics])
    db.commit()
    return subject


# --- history service ---------------------------------------------------------


def test_record_generation_writes_event_and_no_switch_first_time(session: Session) -> None:
    subject = _seed_lane(session, "Physics")
    topic = subject.documents[0].chapters[0].topics[0]
    history.record_generation(
        session, topic_id=topic.id, subject_id=subject.id, provider="gemini_free", seconds=4.2
    )
    events = history.recent_events(session)
    assert len(events) == 1
    assert events[0].event_type is HistoryEventType.topic_generated
    assert events[0].provider_to == "gemini_free"
    assert events[0].detail == "4.2s"


def test_provider_change_records_a_switch_event(session: Session) -> None:
    subject = _seed_lane(session, "Physics", n_topics=2)
    topics = subject.documents[0].chapters[0].topics
    history.record_generation(
        session, topic_id=topics[0].id, subject_id=subject.id, provider="ollama", seconds=30.0
    )
    history.record_generation(
        session, topic_id=topics[1].id, subject_id=subject.id, provider="gemini_free", seconds=3.0
    )
    events = history.recent_events(session)  # newest first
    switch = [e for e in events if e.event_type is HistoryEventType.provider_switch]
    assert len(switch) == 1
    assert switch[0].provider_from == "ollama" and switch[0].provider_to == "gemini_free"
    assert "ollama" in switch[0].detail and "gemini_free" in switch[0].detail


def test_recent_events_view_enriches_names(session: Session) -> None:
    subject = _seed_lane(session, "Physics")
    topic = subject.documents[0].chapters[0].topics[0]
    history.record_generation(
        session, topic_id=topic.id, subject_id=subject.id, provider="gemini_free", seconds=1.0
    )
    view = history.recent_events_view(session)
    assert view[0].subject_name == "Physics"
    assert view[0].topic_title == topic.title


def test_clear_history_scopes_drop_only_their_window(session: Session) -> None:
    from backend.models.processing import HistoryEvent

    # Three events at known ages: 10 min, 5 hours, and 3 days old.
    for delta in (timedelta(minutes=10), timedelta(hours=5), timedelta(days=3)):
        session.add(
            HistoryEvent(
                event_type=HistoryEventType.topic_generated,
                provider_to="gemini_free",
                created_at=T0 - delta,
            )
        )
    session.commit()

    # Last hour: only the 10-minute event goes.
    assert history.clear_history(session, scope="hour", now=T0) == 1
    assert len(history.recent_events(session)) == 2

    # Last day: the 5-hour event goes; the 3-day-old one survives.
    assert history.clear_history(session, scope="day", now=T0) == 1
    remaining = history.recent_events(session)
    assert len(remaining) == 1

    # All: clears the rest.
    assert history.clear_history(session, scope="all") == 1
    assert history.recent_events(session) == []


# --- lane status read model --------------------------------------------------


def test_lane_status_reflects_pause_and_resume(session: Session) -> None:
    subject = _seed_lane(session, "Physics")
    queue = QueueService(session)
    providers = [_FP("gemini_free")]

    assert _lane(queue_view.get_lane_statuses(session, providers)).state == "running"

    queue.pause_lane(subject.id)
    assert _lane(queue_view.get_lane_statuses(session, providers)).state == "paused"

    queue.set_overnight(subject.id, True)
    assert _lane(queue_view.get_lane_statuses(session, providers)).state == "overnight"

    queue.resume_lane(subject.id)
    assert _lane(queue_view.get_lane_statuses(session, providers)).state == "running"


def test_lane_status_reflects_failover_to_second_provider(session: Session) -> None:
    subject = _seed_lane(session, "Physics", n_topics=2)
    topics = subject.documents[0].chapters[0].topics
    # Topic 1 is now running on the failover target (ollama); topic 2 is deferred
    # with the reason the first provider recorded when it hit its limit.
    session.add_all(
        [
            QueueJob(
                topic_id=topics[0].id,
                subject_id=subject.id,
                stage=QueueStage.notes,
                state=QueueState.running,
                assigned_provider="ollama",
            ),
            QueueJob(
                topic_id=topics[1].id,
                subject_id=subject.id,
                stage=QueueStage.notes,
                state=QueueState.pending,
                resume_after=T0 + timedelta(hours=1),
                last_error="gemini_free: 429 quota exceeded",
            ),
        ]
    )
    session.commit()

    status = queue_view.get_lane_statuses(
        session, [_FP("gemini_free"), _FP("ollama")]
    )
    lane = _lane(status)
    assert lane.active_provider == "ollama"  # failed over to provider 2
    states = {p.provider: p.state for p in status.providers}
    assert states["gemini_free"] == "cooling"  # provider 1 is cooling
    assert states["ollama"] == "active"


def test_disabled_provider_shows_disabled(session: Session) -> None:
    _seed_lane(session, "Physics")
    status = queue_view.get_lane_statuses(
        session, [_FP("gemini_free"), _FP("claude_paid", enabled=False)]
    )
    states = {p.provider: p.state for p in status.providers}
    assert states["claude_paid"] == "disabled"


# --- HTTP --------------------------------------------------------------------


def test_http_lane_status_and_controls(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        subject = _seed_lane(db, "Physics")
        subject_id = subject.id

    body = client.get("/api/queue/lanes").json()
    assert any(lane["subject_id"] == subject_id for lane in body["lanes"])
    assert {p["provider"] for p in body["providers"]}  # waterfall strip present

    assert client.post(f"/api/queue/lanes/{subject_id}/pause").status_code == 204
    paused = client.get("/api/queue/lanes").json()["lanes"]
    assert next(lane for lane in paused if lane["subject_id"] == subject_id)["state"] == "paused"

    assert client.post(f"/api/queue/lanes/{subject_id}/resume").status_code == 204
    assert (
        client.post(
            f"/api/queue/lanes/{subject_id}/overnight", json={"enabled": True}
        ).status_code
        == 204
    )
    overnight = client.get("/api/queue/lanes").json()["lanes"]
    assert next(lane for lane in overnight if lane["subject_id"] == subject_id)["state"] == "overnight"


def test_http_lane_control_unknown_subject_404(client: TestClient) -> None:
    assert client.post("/api/queue/lanes/999/pause").status_code == 404


def test_http_history_endpoint(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        subject = _seed_lane(db, "Physics")
        topic = subject.documents[0].chapters[0].topics[0]
        history.record_generation(
            db, topic_id=topic.id, subject_id=subject.id, provider="gemini_free", seconds=2.0
        )

    events = client.get("/api/queue/history").json()
    assert len(events) == 1
    assert events[0]["event_type"] == "topic_generated"
    assert events[0]["subject_name"] == "Physics"


def test_http_clear_history(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        subject = _seed_lane(db, "Physics", n_topics=2)
        topics = subject.documents[0].chapters[0].topics
        for topic in topics:
            history.record_generation(
                db, topic_id=topic.id, subject_id=subject.id, provider="gemini_free", seconds=1.0
            )

    assert len(client.get("/api/queue/history").json()) == 2

    cleared = client.delete("/api/queue/history?scope=all")
    assert cleared.status_code == 200
    assert cleared.json() == {"scope": "all", "deleted": 2}
    assert client.get("/api/queue/history").json() == []


def _lane(status: queue_view.LaneQueueStatus) -> queue_view.LaneStatus:
    assert len(status.lanes) == 1
    return status.lanes[0]
