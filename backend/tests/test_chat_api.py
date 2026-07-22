"""Tests for the AI assistant chat (`/api/chat`): service + router.

Providers are faked by monkeypatching the ``services.chat._build_waterfall``
seam with a waterfall of ``MockProvider``s — no network, no SDKs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.models.chat import ChatMessage, ChatSession
from backend.services import chat as chatsvc
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall


def _fake_waterfall(*providers: MockProvider):
    """A ``_build_waterfall`` stand-in returning a fixed waterfall."""

    def _build(_settings) -> Waterfall:
        return Waterfall(list(providers))

    return _build


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> MockProvider:
    provider = MockProvider("mock_free", text="The mitochondria is the powerhouse.")
    monkeypatch.setattr(chatsvc, "_build_waterfall", _fake_waterfall(provider))
    return provider


def test_send_creates_session_and_replies(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    res = client.post("/api/chat", json={"message": "What is a mitochondrion?"})
    assert res.status_code == 200
    body = res.json()
    assert body["session_id"] == 1
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "The mitochondria is the powerhouse."
    assert body["message"]["provider"] == "mock_free"

    # Both turns are persisted, in order, under a titled session.
    with db_factory() as db:
        chat = db.get(ChatSession, 1)
        assert chat is not None
        assert chat.title == "What is a mitochondrion?"
        assert [(m.role, m.content) for m in chat.messages] == [
            ("user", "What is a mitochondrion?"),
            ("assistant", "The mitochondria is the powerhouse."),
        ]


def test_send_continues_existing_session_with_history(
    client: TestClient, fake_provider: MockProvider
) -> None:
    first = client.post("/api/chat", json={"message": "Define osmosis."})
    session_id = first.json()["session_id"]

    res = client.post(
        "/api/chat", json={"session_id": session_id, "message": "Give an example."}
    )
    assert res.status_code == 200
    assert res.json()["session_id"] == session_id
    # The prompt carries the earlier turns and ends on the assistant cue.
    prompt = fake_provider.last_prompt
    assert prompt is not None
    assert "Student: Define osmosis." in prompt
    assert "Student: Give an example." in prompt
    assert prompt.endswith("Assistant:")


def test_send_unknown_session_404s(
    client: TestClient, fake_provider: MockProvider
) -> None:
    res = client.post("/api/chat", json={"session_id": 999, "message": "hi"})
    assert res.status_code == 404


def test_send_pinned_provider_skips_cheaper_tiers(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    free = MockProvider("mock_free", text="free answer")
    local = MockProvider("mock_local", text="local answer")
    monkeypatch.setattr(chatsvc, "_build_waterfall", _fake_waterfall(free, local))

    res = client.post("/api/chat", json={"message": "hi", "provider": "mock_local"})
    assert res.status_code == 200
    assert res.json()["message"]["provider"] == "mock_local"
    assert free.generate_calls == 0
    assert local.generate_calls == 1


def test_send_unknown_provider_400s(
    client: TestClient, fake_provider: MockProvider
) -> None:
    res = client.post("/api/chat", json={"message": "hi", "provider": "claude_paid"})
    assert res.status_code == 400
    assert "claude_paid" in res.json()["detail"]


def test_send_exhausted_providers_503_and_keeps_user_turn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_factory: sessionmaker
) -> None:
    dead = MockProvider("mock_free", available=False, headroom=0)
    monkeypatch.setattr(chatsvc, "_build_waterfall", _fake_waterfall(dead))

    res = client.post("/api/chat", json={"message": "hello?"})
    assert res.status_code == 503
    # The user turn was committed before the provider call and survives.
    with db_factory() as db:
        roles = [m.role for m in db.query(ChatMessage).all()]
        assert roles == ["user"]


def test_prompt_carries_persona_and_language(
    client: TestClient, fake_provider: MockProvider
) -> None:
    client.patch("/api/settings", json={"language": "it", "study_field": "law"})
    client.post("/api/chat", json={"message": "Cos'è un contratto?"})
    prompt = fake_provider.last_prompt
    assert prompt is not None
    assert "law tutor" in prompt
    assert "Italian" in prompt


def test_prompt_drops_oldest_turns_beyond_char_cap(
    client: TestClient, fake_provider: MockProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(chatsvc, "MAX_HISTORY_CHARS", 200)
    first = client.post("/api/chat", json={"message": "A" * 150})
    session_id = first.json()["session_id"]
    client.post("/api/chat", json={"session_id": session_id, "message": "B" * 150})

    prompt = fake_provider.last_prompt
    assert prompt is not None
    assert "B" * 150 in prompt  # newest turn always survives
    assert "A" * 150 not in prompt  # oldest dropped by the cap


def test_deleting_session_cascades_messages(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    client.post("/api/chat", json={"message": "hi"})
    with db_factory() as db:
        db.delete(db.get(ChatSession, 1))
        db.commit()
        assert db.query(ChatMessage).count() == 0


# --- Step 2: history, eviction, retention ------------------------------------


def test_history_lists_last_five_newest_first_and_evicts_oldest(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    for i in range(6):
        res = client.post("/api/chat", json={"message": f"question {i}"})
        assert res.status_code == 200

    res = client.get("/api/chat/sessions")
    assert res.status_code == 200
    sessions = res.json()
    assert len(sessions) == 5
    assert [s["title"] for s in sessions] == [
        "question 5",
        "question 4",
        "question 3",
        "question 2",
        "question 1",
    ]
    # The 6th session evicted the oldest — its rows (and messages) are gone.
    with db_factory() as db:
        assert db.query(ChatSession).count() == 5
        assert db.query(ChatMessage).filter_by(content="question 0").count() == 0


def test_continuing_a_session_does_not_evict(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    first = client.post("/api/chat", json={"message": "original"})
    session_id = first.json()["session_id"]
    for i in range(4):
        client.post("/api/chat", json={"message": f"filler {i}"})
    # 5 sessions exist; sending into the oldest one must not create/evict.
    res = client.post(
        "/api/chat", json={"session_id": session_id, "message": "follow-up"}
    )
    assert res.status_code == 200
    with db_factory() as db:
        assert db.query(ChatSession).count() == 5


def test_get_session_returns_full_transcript(
    client: TestClient, fake_provider: MockProvider
) -> None:
    created = client.post("/api/chat", json={"message": "hi", "provider": "mock_free"})
    session_id = created.json()["session_id"]

    res = client.get(f"/api/chat/sessions/{session_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "hi"
    assert body["provider"] == "mock_free"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]

    assert client.get("/api/chat/sessions/999").status_code == 404


def test_delete_session_endpoint(
    client: TestClient, fake_provider: MockProvider
) -> None:
    session_id = client.post("/api/chat", json={"message": "hi"}).json()["session_id"]
    assert client.delete(f"/api/chat/sessions/{session_id}").status_code == 204
    assert client.get(f"/api/chat/sessions/{session_id}").status_code == 404
    assert client.delete(f"/api/chat/sessions/{session_id}").status_code == 404


def _age_session(db_factory: sessionmaker, session_id: int, *, hours: float) -> None:
    """Backdate a session's last activity by ``hours``."""
    from datetime import timedelta

    from backend.models.hierarchy import utcnow

    with db_factory() as db:
        chat = db.get(ChatSession, session_id)
        chat.updated_at = utcnow() - timedelta(hours=hours)
        db.commit()


def test_cleanup_time_window_expires_idle_sessions_only(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    old = client.post("/api/chat", json={"message": "old"}).json()["session_id"]
    fresh = client.post("/api/chat", json={"message": "fresh"}).json()["session_id"]
    _age_session(db_factory, old, hours=2)
    client.patch("/api/settings", json={"chat_retention": "after_1_hour"})

    with db_factory() as db:
        deleted = chatsvc.cleanup_sessions(db)
        assert deleted == 1
        assert db.get(ChatSession, old) is None
        assert db.get(ChatSession, fresh) is not None


def test_cleanup_keep_last_5_never_time_expires(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    session_id = client.post("/api/chat", json={"message": "hi"}).json()["session_id"]
    _age_session(db_factory, session_id, hours=100)
    with db_factory() as db:
        assert chatsvc.cleanup_sessions(db) == 0
        assert chatsvc.cleanup_sessions(db, at_startup=True) == 0
        assert db.get(ChatSession, session_id) is not None


def test_cleanup_on_close_purges_only_at_startup(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    client.post("/api/chat", json={"message": "hi"})
    client.patch("/api/settings", json={"chat_retention": "on_close"})

    with db_factory() as db:
        # Periodic pass while the app runs: must not touch live sessions.
        assert chatsvc.cleanup_sessions(db) == 0
        assert db.query(ChatSession).count() == 1
        # Startup pass: the previous run's chats are purged.
        assert chatsvc.cleanup_sessions(db, at_startup=True) == 1
        assert db.query(ChatSession).count() == 0


def test_settings_chat_retention_roundtrip(client: TestClient) -> None:
    assert client.get("/api/settings").json()["chat_retention"] == "keep_last_5"
    res = client.patch("/api/settings", json={"chat_retention": "after_1_day"})
    assert res.status_code == 200
    assert res.json()["chat_retention"] == "after_1_day"
    # Unknown values are rejected by the Literal validator.
    assert (
        client.patch("/api/settings", json={"chat_retention": "forever"}).status_code
        == 422
    )


# --- Stop: the reply that lands after a stop is discarded, never stored -------


def test_stop_discards_the_reply_but_keeps_the_user_turn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_factory: sessionmaker
) -> None:
    """A stop *during* the provider call must not persist the answer."""
    provider = MockProvider("mock_free", text="an answer nobody is waiting for")

    # Stop arrives while the provider is working — the realistic ordering.
    original = provider.generate

    def _generate_then_stop(*args, **kwargs):
        stop = client.post("/api/chat/stop", json={"request_id": "req-1"}).json()
        assert stop["stopped"] is True
        # The session id comes back so a stopped first send isn't orphaned.
        assert stop["session_id"] == 1
        return original(*args, **kwargs)

    monkeypatch.setattr(provider, "generate", _generate_then_stop)
    monkeypatch.setattr(chatsvc, "_build_waterfall", _fake_waterfall(provider))

    res = client.post(
        "/api/chat", json={"message": "slow one?", "request_id": "req-1"}
    )
    assert res.status_code == 409
    with db_factory() as db:
        roles = [m.role for m in db.query(ChatMessage).all()]
        assert roles == ["user"]  # the question stays; the answer never lands


def test_stopping_an_unknown_request_is_a_no_op(client: TestClient) -> None:
    res = client.post("/api/chat/stop", json={"request_id": "never-ran"})
    assert res.status_code == 200
    assert res.json() == {"stopped": False, "session_id": None}


def test_a_send_that_is_not_stopped_still_stores_its_reply(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    res = client.post("/api/chat", json={"message": "hi", "request_id": "req-2"})
    assert res.status_code == 200
    # The id is retired once the reply lands: a late stop finds nothing.
    assert client.post("/api/chat/stop", json={"request_id": "req-2"}).json() == {
        "stopped": False,
        "session_id": None,
    }
    with db_factory() as db:
        assert [m.role for m in db.query(ChatMessage).all()] == ["user", "assistant"]


def test_the_assistant_can_close_a_session_and_the_marker_is_stripped(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_factory: sessionmaker
) -> None:
    """Last-resort close: the goodbye is kept, the sentinel never reaches the UI."""
    provider = MockProvider(
        "mock_free", text=f"I'm ending this conversation here.\n{chatsvc.CLOSE_SENTINEL}"
    )
    monkeypatch.setattr(chatsvc, "_build_waterfall", _fake_waterfall(provider))

    body = client.post("/api/chat", json={"message": "insult"}).json()
    assert body["closed"] is True
    assert body["message"]["content"] == "I'm ending this conversation here."

    with db_factory() as db:
        chat = db.get(ChatSession, body["session_id"])
        assert chat is not None and chat.closed_at is not None


def test_a_closed_session_refuses_further_sends(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    session_id = client.post("/api/chat", json={"message": "hi"}).json()["session_id"]
    with db_factory() as db:
        from backend.models.hierarchy import utcnow

        db.get(ChatSession, session_id).closed_at = utcnow()
        db.commit()

    res = client.post(
        "/api/chat", json={"session_id": session_id, "message": "let me back in"}
    )
    assert res.status_code == 409
    # The refused message was never even recorded as a user turn.
    with db_factory() as db:
        assert [m.role for m in db.query(ChatMessage).all()] == ["user", "assistant"]
    # The transcript is still readable, and a brand new chat still works.
    assert client.get(f"/api/chat/sessions/{session_id}").status_code == 200
    assert client.post("/api/chat", json={"message": "fresh start"}).status_code == 200


def test_an_ordinary_reply_never_closes_the_session(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    body = client.post("/api/chat", json={"message": "what is osmosis?"}).json()
    assert body["closed"] is False
    with db_factory() as db:
        assert db.get(ChatSession, body["session_id"]).closed_at is None
