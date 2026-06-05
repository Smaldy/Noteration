"""Settings service + HTTP tests (Phase 9f): read singleton + partial update."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app
from backend.models.settings import Settings
from backend.services import settings as settings_service


# --- service unit tests ------------------------------------------------------


def test_get_settings_creates_singleton_with_defaults(session: Session) -> None:
    s = settings_service.get_settings(session)
    assert s.id == 1
    assert s.allow_paid is False
    assert s.pomodoro_work_min == 25
    assert s.theme == "system"
    assert s.gemini_model == "gemini-2.5-flash-lite"  # cheapest default
    assert s.per_document_token_budget == 0  # 0 = automatic ceiling
    # Idempotent — a second call returns the same row, not a new one.
    assert settings_service.get_settings(session).id == 1
    assert session.query(Settings).count() == 1


def test_update_applies_only_given_fields(session: Session) -> None:
    settings_service.get_settings(session)
    updated = settings_service.update_settings(
        session, {"allow_paid": True, "theme": "dark"}
    )
    assert updated.allow_paid is True
    assert updated.theme == "dark"
    assert updated.pomodoro_work_min == 25  # untouched


def test_update_blank_key_clears_it(session: Session) -> None:
    settings_service.update_settings(session, {"api_key_gemini": "secret-123"})
    assert settings_service.get_settings(session).api_key_gemini == "secret-123"
    settings_service.update_settings(session, {"api_key_gemini": ""})
    assert settings_service.get_settings(session).api_key_gemini is None


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


def test_http_get_defaults(client: TestClient) -> None:
    response = client.get("/api/settings")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["theme"] == "system"
    assert body["gemini_key_set"] is False
    assert "api_key_gemini" not in body  # secret never echoed


def test_http_patch_sets_key_masked(client: TestClient) -> None:
    response = client.patch("/api/settings", json={"api_key_claude": "sk-abc"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["claude_key_set"] is True
    assert "api_key_claude" not in body


def test_http_patch_validates_pomodoro(client: TestClient) -> None:
    assert client.patch("/api/settings", json={"pomodoro_work_min": 0}).status_code == 422


def test_http_patch_validates_theme(client: TestClient) -> None:
    assert client.patch("/api/settings", json={"theme": "neon"}).status_code == 422


def test_http_patch_sets_gemini_model(client: TestClient) -> None:
    response = client.patch("/api/settings", json={"gemini_model": "gemini-2.5-flash"})
    assert response.status_code == 200, response.text
    assert response.json()["gemini_model"] == "gemini-2.5-flash"


def test_http_patch_rejects_unknown_gemini_model(client: TestClient) -> None:
    response = client.patch("/api/settings", json={"gemini_model": "gemini-2.0-flash"})
    assert response.status_code == 422  # only the offered 2.5 models are allowed


def test_http_patch_sets_per_document_token_budget(client: TestClient) -> None:
    response = client.patch(
        "/api/settings", json={"per_document_token_budget": 50000}
    )
    assert response.status_code == 200, response.text
    assert response.json()["per_document_token_budget"] == 50000


def test_http_patch_rejects_negative_token_budget(client: TestClient) -> None:
    response = client.patch("/api/settings", json={"per_document_token_budget": -1})
    assert response.status_code == 422


# --- notes length (pages of content per topic) ------------------------------- #


def test_http_get_note_length_default(client: TestClient) -> None:
    assert client.get("/api/settings").json()["note_length"] == 3


def test_http_patch_sets_note_length(client: TestClient) -> None:
    response = client.patch("/api/settings", json={"note_length": 8})
    assert response.status_code == 200, response.text
    assert response.json()["note_length"] == 8


def test_http_patch_rejects_out_of_range_note_length(client: TestClient) -> None:
    assert client.patch("/api/settings", json={"note_length": 0}).status_code == 422
    assert client.patch("/api/settings", json={"note_length": 11}).status_code == 422


# --- calendar hourly Day-view config ---------------------------------------- #


def test_http_get_calendar_defaults(client: TestClient) -> None:
    body = client.get("/api/settings").json()
    assert body["calendar_day_start_hour"] == 8
    assert body["calendar_day_end_hour"] == 23
    assert body["calendar_slot_minutes"] == 60


def test_http_patch_sets_calendar_window(client: TestClient) -> None:
    response = client.patch(
        "/api/settings",
        json={
            "calendar_day_start_hour": 6,
            "calendar_day_end_hour": 22,
            "calendar_slot_minutes": 30,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["calendar_day_start_hour"] == 6
    assert body["calendar_day_end_hour"] == 22
    assert body["calendar_slot_minutes"] == 30


def test_http_patch_rejects_inverted_window(client: TestClient) -> None:
    response = client.patch(
        "/api/settings",
        json={"calendar_day_start_hour": 20, "calendar_day_end_hour": 8},
    )
    assert response.status_code == 422  # end must exceed start


def test_http_patch_rejects_unknown_slot_size(client: TestClient) -> None:
    response = client.patch("/api/settings", json={"calendar_slot_minutes": 45})
    assert response.status_code == 422  # only 15/30/60/90/120 allowed


# --- language (UI + AI-content) --------------------------------------------- #


def test_get_settings_default_language_is_english(session: Session) -> None:
    assert settings_service.get_settings(session).language == "en"


def test_http_get_language_default(client: TestClient) -> None:
    assert client.get("/api/settings").json()["language"] == "en"


def test_http_patch_sets_language(client: TestClient) -> None:
    for code in ("it", "es", "en"):
        response = client.patch("/api/settings", json={"language": code})
        assert response.status_code == 200, response.text
        assert response.json()["language"] == code


def test_http_patch_rejects_unknown_language(client: TestClient) -> None:
    assert client.patch("/api/settings", json={"language": "fr"}).status_code == 422
