"""Arcade minigame service + HTTP tests (additive feature layer).

Covers the coin economy, run lifecycle, upgrades, the daily quest, and the
anti-binge cooldown. The game loop runs in the browser; these prove the server
owns currency/records/cooldown correctly.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app
from backend.models.arcade import ArcadeState
from backend.services import arcade as arcade_service


# --- service unit tests ------------------------------------------------------


def test_get_state_creates_singleton_with_defaults(session: Session) -> None:
    state = arcade_service.get_state(session)
    assert state.id == 1
    assert state.coins == 0
    assert state.score_balance == 0
    assert state.high_score == 0
    assert state.wave_record == 0
    assert state.resumable_wave == 0
    # Idempotent.
    assert arcade_service.get_state(session).id == 1
    assert session.query(ArcadeState).count() == 1


def test_earn_flashcard_adds_coins(session: Session) -> None:
    state = arcade_service.earn_coins(session, source="flashcard", count=3)
    assert state.coins == 3 * arcade_service.COIN_PER_FLASHCARD


def test_earn_mcq_advances_daily_quest_and_grants_bonus_once(session: Session) -> None:
    target = arcade_service.DAILY_MCQ_TARGET
    state = arcade_service.earn_coins(session, source="mcq", count=target - 1)
    assert state.daily_mcq_count == target - 1
    assert state.daily_bonus_claimed is False
    coins_before_bonus = state.coins

    # The MCQ that hits the target grants the bonus coin (in addition to its own).
    state = arcade_service.earn_coins(session, source="mcq", count=1)
    assert state.daily_mcq_count == target
    assert state.daily_bonus_claimed is True
    assert state.coins == coins_before_bonus + arcade_service.COIN_PER_MCQ + arcade_service.DAILY_BONUS_COINS

    # Further MCQs the same day don't re-grant the bonus.
    state = arcade_service.earn_coins(session, source="mcq", count=5)
    assert state.coins == coins_before_bonus + arcade_service.COIN_PER_MCQ * 6 + arcade_service.DAILY_BONUS_COINS


def test_daily_quest_resets_on_new_day(session: Session) -> None:
    state = arcade_service.get_state(session)
    state.daily_quest_date = arcade_service._today() - timedelta(days=1)
    state.daily_mcq_count = 9
    state.daily_bonus_claimed = True
    session.commit()

    state = arcade_service.earn_coins(session, source="mcq", count=1)
    assert state.daily_mcq_count == 1  # reset, then this one counted
    assert state.daily_bonus_claimed is False


def test_resume_cost_is_base_plus_wave() -> None:
    assert arcade_service.resume_cost(5) == arcade_service.BASE_COST + 5


def test_start_fresh_deducts_base_cost_and_opens_session(session: Session) -> None:
    arcade_service.earn_coins(session, source="flashcard", count=50)
    run = arcade_service.start_run(session, mode="fresh")
    assert run.start_wave == 1
    assert run.cost == arcade_service.BASE_COST
    assert run.coins_after == 50 - arcade_service.BASE_COST
    assert run.session_id > 0


def test_start_fresh_without_coins_raises(session: Session) -> None:
    with pytest.raises(arcade_service.InsufficientCoinsError):
        arcade_service.start_run(session, mode="fresh")


def test_start_resume_requires_saved_run(session: Session) -> None:
    arcade_service.earn_coins(session, source="flashcard", count=50)
    with pytest.raises(arcade_service.NothingToResumeError):
        arcade_service.start_run(session, mode="resume")


def test_resume_costs_base_plus_wave_and_consumes_saved_run(session: Session) -> None:
    state = arcade_service.get_state(session)
    state.coins = 100
    state.resumable_wave = 5
    state.resumable_score = 200
    session.commit()

    run = arcade_service.start_run(session, mode="resume")
    assert run.start_wave == 5
    assert run.start_score == 200
    assert run.cost == arcade_service.BASE_COST + 5
    state = arcade_service.get_state(session)
    assert state.coins == 100 - (arcade_service.BASE_COST + 5)
    assert state.resumable_wave == 0  # consumed


def test_end_run_banks_score_updates_records_and_saves_resume_on_death(
    session: Session,
) -> None:
    arcade_service.earn_coins(session, source="flashcard", count=50)
    run = arcade_service.start_run(session, mode="fresh")
    state = arcade_service.end_run(
        session, session_id=run.session_id, wave_reached=4, score_earned=120, died=True
    )
    assert state.score_balance == 120
    assert state.high_score == 120
    assert state.wave_record == 4
    assert state.resumable_wave == 4
    assert state.resumable_score == 120


def test_end_run_twice_is_rejected(session: Session) -> None:
    arcade_service.earn_coins(session, source="flashcard", count=50)
    run = arcade_service.start_run(session, mode="fresh")
    arcade_service.end_run(
        session, session_id=run.session_id, wave_reached=1, score_earned=10, died=True
    )
    with pytest.raises(arcade_service.SessionNotFoundError):
        arcade_service.end_run(
            session, session_id=run.session_id, wave_reached=1, score_earned=10, died=True
        )


def test_buy_upgrade_spends_score_and_levels_up(session: Session) -> None:
    state = arcade_service.get_state(session)
    state.score_balance = 500
    session.commit()

    state = arcade_service.buy_upgrade(session, key="max_health")
    assert state.score_balance == 500 - 50  # first level cost
    levels = arcade_service._upgrade_levels(session)
    assert levels["max_health"] == 1

    arcade_service.buy_upgrade(session, key="max_health")
    levels_after = arcade_service._upgrade_levels(session)
    assert levels_after["max_health"] == 2


def test_buy_upgrade_errors(session: Session) -> None:
    state = arcade_service.get_state(session)
    state.score_balance = 10
    session.commit()
    with pytest.raises(arcade_service.InsufficientScoreError):
        arcade_service.buy_upgrade(session, key="max_health")
    with pytest.raises(arcade_service.UnknownUpgradeError):
        arcade_service.buy_upgrade(session, key="nope")

    # Single-level upgrade maxes out after one purchase.
    state.score_balance = 1000
    session.commit()
    arcade_service.buy_upgrade(session, key="shooting")
    with pytest.raises(arcade_service.UpgradeMaxedError):
        arcade_service.buy_upgrade(session, key="shooting")


def test_cooldown_triggers_after_too_many_runs(session: Session) -> None:
    arcade_service.earn_coins(session, source="flashcard", count=200)
    assert arcade_service.cooldown_until(session) is None
    for _ in range(arcade_service.MAX_RUNS_PER_WINDOW):
        arcade_service.start_run(session, mode="fresh")
    # Window is now full → cooldown active, lever locked.
    assert arcade_service.cooldown_until(session) is not None
    with pytest.raises(arcade_service.CooldownActiveError):
        arcade_service.start_run(session, mode="fresh")


# --- HTTP tests (shared in-memory DB via StaticPool) -------------------------


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


def test_http_get_state_defaults(client: TestClient) -> None:
    body = client.get("/api/arcade/state").json()
    assert body["coins"] == 0
    assert body["resume_cost"] is None
    assert body["cooldown_until"] is None
    assert body["daily_quest"]["target"] == arcade_service.DAILY_MCQ_TARGET
    keys = {u["key"] for u in body["upgrades"]}
    assert "max_health" in keys and "shooting" in keys
    assert body["economy"]["base_cost"] == arcade_service.BASE_COST


def test_http_earn_flashcard(client: TestClient) -> None:
    body = client.post("/api/arcade/coins/earn", json={"source": "flashcard"}).json()
    assert body["coins"] == arcade_service.COIN_PER_FLASHCARD


def test_http_earn_rejects_bad_source_and_count(client: TestClient) -> None:
    assert client.post("/api/arcade/coins/earn", json={"source": "bogus"}).status_code == 422
    assert (
        client.post("/api/arcade/coins/earn", json={"source": "mcq", "count": 0}).status_code
        == 422
    )


def test_http_start_without_coins_is_402(client: TestClient) -> None:
    resp = client.post("/api/arcade/run/start", json={"mode": "fresh"})
    assert resp.status_code == 402


def test_http_full_run_cycle(client: TestClient) -> None:
    # Earn enough to play.
    client.post("/api/arcade/coins/earn", json={"source": "flashcard", "count": 50})
    start = client.post("/api/arcade/run/start", json={"mode": "fresh"})
    assert start.status_code == 200, start.text
    sid = start.json()["session_id"]
    assert start.json()["cost"] == arcade_service.BASE_COST

    end = client.post(
        "/api/arcade/run/end",
        json={"session_id": sid, "wave_reached": 3, "score_earned": 90, "died": True},
    )
    assert end.status_code == 200, end.text
    state = end.json()
    assert state["high_score"] == 90
    assert state["wave_record"] == 3
    assert state["resumable_wave"] == 3
    assert state["resume_cost"] == arcade_service.BASE_COST + 3


def test_http_buy_upgrade_flow(client: TestClient) -> None:
    # Bank score via a run, then spend it.
    client.post("/api/arcade/coins/earn", json={"source": "flashcard", "count": 50})
    sid = client.post("/api/arcade/run/start", json={"mode": "fresh"}).json()["session_id"]
    client.post(
        "/api/arcade/run/end",
        json={"session_id": sid, "wave_reached": 9, "score_earned": 400, "died": True},
    )
    buy = client.post("/api/arcade/upgrades/max_health/buy")
    assert buy.status_code == 200, buy.text
    body = buy.json()
    health = next(u for u in body["upgrades"] if u["key"] == "max_health")
    assert health["level"] == 1
    assert body["score_balance"] == 400 - 50

    assert client.post("/api/arcade/upgrades/nope/buy").status_code == 404


def test_dev_grant_tops_up_coins_and_score(session: Session) -> None:
    state = arcade_service.dev_grant(session)
    assert state.coins == arcade_service.DEV_GRANT_AMOUNT
    assert state.score_balance == arcade_service.DEV_GRANT_AMOUNT


def test_dev_reset_upgrades_clears_levels(session: Session) -> None:
    arcade_service.dev_grant(session)
    arcade_service.buy_upgrade(session, key="max_health")
    assert arcade_service._upgrade_levels(session).get("max_health") == 1

    arcade_service.dev_reset_upgrades(session)
    assert arcade_service._upgrade_levels(session) == {}


def test_http_dev_endpoints(client: TestClient) -> None:
    grant = client.post("/api/arcade/dev/grant")
    assert grant.status_code == 200, grant.text
    body = grant.json()
    assert body["coins"] == arcade_service.DEV_GRANT_AMOUNT
    assert body["score_balance"] == arcade_service.DEV_GRANT_AMOUNT

    # Buy then reset — the upgrade should drop back to level 0.
    client.post("/api/arcade/upgrades/shooting/buy")
    reset = client.post("/api/arcade/dev/reset-upgrades")
    assert reset.status_code == 200, reset.text
    shooting = next(u for u in reset.json()["upgrades"] if u["key"] == "shooting")
    assert shooting["level"] == 0
