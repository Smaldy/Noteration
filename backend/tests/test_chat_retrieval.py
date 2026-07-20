"""Reference-topic grounding for the assistant sidebar (Step 6).

Covers the retrieval module (chunking, BM25 selection, budgeting) and the chat
service's use of it: the pin is carried per send like ``provider``, its material
lands in the prompt, and it spends the history budget instead of extending it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models import Chapter, Document, Flashcard, Note, Subject, Topic
from backend.models.chat import ChatSession
from backend.services import chat as chatsvc
from backend.services import retrieval
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall

NOTES_MD = """
## Osmosis
Water moves across a semipermeable membrane toward the higher solute
concentration. The driving force is the water potential gradient.

## Diffusion
Solute particles spread from high to low concentration until evenly mixed.
Diffusion needs no membrane and no energy input.

## Active transport
Protein pumps move solutes against their gradient, burning ATP to do it.
This is the only transport mode here that has an energy cost.
""".strip()


def _seed_topic(db: Session, *, notes: str = NOTES_MD) -> int:
    """Biology › cells.pdf › Cell transport › Membrane transport, with notes."""
    subject = Subject(name="Biology")
    db.add(subject)
    db.flush()
    doc = Document(subject=subject, filename="cells.pdf", file_hash="h1")
    db.add(doc)
    db.flush()
    chapter = Chapter(document=doc, subject=subject, title="Cell transport")
    db.add(chapter)
    db.flush()
    topic = Topic(chapter=chapter, title="Membrane transport")
    db.add(topic)
    db.flush()
    if notes:
        db.add(Note(topic_id=topic.id, content_md=notes))
    db.commit()
    return topic.id


def _fake_waterfall(*providers: MockProvider):
    def _build(_settings) -> Waterfall:
        return Waterfall(list(providers))

    return _build


@pytest.fixture
def fake_provider(monkeypatch: pytest.MonkeyPatch) -> MockProvider:
    provider = MockProvider("mock_free", text="Grounded answer.")
    monkeypatch.setattr(chatsvc, "_build_waterfall", _fake_waterfall(provider))
    return provider


# --- retrieval ---------------------------------------------------------------


def test_chunks_split_on_headings_and_carry_them(session: Session) -> None:
    topic_id = _seed_topic(session)
    ctx = retrieval.build_topic_context(session, topic_id, query="osmosis")
    assert ctx is not None
    assert ctx.total_chunks == 3  # one per heading section
    assert ctx.path == "Biology › cells.pdf › Cell transport › Membrane transport"
    assert "### Osmosis" in ctx.extract  # the heading rides along with its body


def test_ranking_puts_the_queried_section_first_within_a_tight_budget(
    session: Session,
) -> None:
    topic_id = _seed_topic(session)
    # Room for roughly one chunk: the ranker must spend it on the right one.
    ctx = retrieval.build_topic_context(
        session, topic_id, query="Why do pumps need ATP?", max_chars=220
    )
    assert ctx is not None
    assert ctx.used_chunks == 1
    assert "Active transport" in ctx.extract
    assert "Diffusion" not in ctx.extract
    # Everything dropped for length is marked, not silently elided.
    assert ctx.extract.startswith("[…]")


def test_quoted_emitter_turn_still_ranks_on_its_source_text(session: Session) -> None:
    topic_id = _seed_topic(session)
    # An aiContext turn: the signal is in the quote, not in the instruction.
    query = "> Define osmosis.\n> Water crossing a membrane.\n\nTake me deeper."
    ctx = retrieval.build_topic_context(session, topic_id, query=query, max_chars=220)
    assert ctx is not None
    assert "Osmosis" in ctx.extract


def test_no_lexical_signal_reads_the_topic_from_the_top(session: Session) -> None:
    topic_id = _seed_topic(session)
    ctx = retrieval.build_topic_context(
        session, topic_id, query="explain this to me", max_chars=220
    )
    assert ctx is not None
    assert ctx.used_chunks == 1
    assert "Osmosis" in ctx.extract  # document order, not a noise ranking
    assert not ctx.extract.startswith("[…]")


def test_flashcards_ground_a_topic_with_no_notes(session: Session) -> None:
    topic_id = _seed_topic(session, notes="")
    session.add(
        Flashcard(
            topic_id=topic_id,
            front="Define osmosis.",
            back="Water crossing a semipermeable membrane toward higher solute.",
        )
    )
    session.commit()

    ctx = retrieval.build_topic_context(session, topic_id, query="osmosis")
    assert ctx is not None
    assert ctx.used_chunks == 1
    assert "Key facts" in ctx.extract
    assert "semipermeable membrane" in ctx.extract


def test_empty_topic_yields_a_path_but_no_extract(session: Session) -> None:
    topic_id = _seed_topic(session, notes="")
    ctx = retrieval.build_topic_context(session, topic_id, query="anything")
    assert ctx is not None
    assert ctx.extract == ""
    assert ctx.total_chunks == 0
    assert ctx.path.endswith("Membrane transport")


def test_missing_topic_returns_none(session: Session) -> None:
    assert retrieval.build_topic_context(session, 999, query="hi") is None


def test_long_section_is_split_at_paragraph_boundaries(session: Session) -> None:
    paragraphs = "\n\n".join(f"Paragraph {i} about mitosis." * 20 for i in range(6))
    topic_id = _seed_topic(session, notes=f"## Cell cycle\n{paragraphs}")
    ctx = retrieval.build_topic_context(session, topic_id, query="mitosis")
    assert ctx is not None
    assert ctx.total_chunks > 1  # one heading, several chunks
    assert all(
        len(chunk) <= retrieval.CHUNK_MAX_CHARS + 200
        for chunk in ctx.extract.split("\n\n### ")
    )


# --- chat integration --------------------------------------------------------


def test_pinned_topic_grounds_the_prompt(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    with db_factory() as db:
        topic_id = _seed_topic(db)

    res = client.post(
        "/api/chat", json={"message": "How does water cross?", "topic_id": topic_id}
    )
    assert res.status_code == 200

    prompt = fake_provider.last_prompt
    assert prompt is not None
    assert "# Reference topic: Biology › cells.pdf › Cell transport" in prompt
    assert "semipermeable membrane" in prompt  # the retrieved material itself
    assert "Ground your answer in the material below" in prompt
    assert prompt.endswith("Assistant:")


def test_pin_is_stored_and_restored_and_can_be_removed(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    with db_factory() as db:
        topic_id = _seed_topic(db)

    session_id = client.post(
        "/api/chat", json={"message": "first", "topic_id": topic_id}
    ).json()["session_id"]

    # Reopening restores the chip, label included.
    body = client.get(f"/api/chat/sessions/{session_id}").json()
    assert body["topic_id"] == topic_id
    assert body["topic_title"] == "Membrane transport"

    # Removing the chip (✕) means the next send carries no topic.
    client.post("/api/chat", json={"session_id": session_id, "message": "second"})
    assert "# Reference topic" not in (fake_provider.last_prompt or "")
    body = client.get(f"/api/chat/sessions/{session_id}").json()
    assert body["topic_id"] is None
    assert body["topic_title"] is None


def test_unknown_pinned_topic_404s(
    client: TestClient, fake_provider: MockProvider
) -> None:
    res = client.post("/api/chat", json={"message": "hi", "topic_id": 999})
    assert res.status_code == 404
    assert fake_provider.generate_calls == 0


def test_deleting_the_topic_unpins_but_keeps_the_conversation(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    with db_factory() as db:
        topic_id = _seed_topic(db)
    session_id = client.post(
        "/api/chat", json={"message": "hi", "topic_id": topic_id}
    ).json()["session_id"]

    with db_factory() as db:
        db.delete(db.get(Topic, topic_id))
        db.commit()
        chat = db.get(ChatSession, session_id)
        assert chat is not None  # SET NULL, not CASCADE
        assert chat.topic_id is None
        assert len(chat.messages) == 2


def test_reference_material_spends_the_history_budget(
    client: TestClient, fake_provider: MockProvider, db_factory: sessionmaker
) -> None:
    # The envelope only holds if the two shares fit inside the ceiling.
    assert (
        retrieval.CONTEXT_MAX_CHARS + chatsvc.MIN_HISTORY_CHARS
        <= chatsvc.MAX_HISTORY_CHARS
    )

    # A topic with far more material than the context budget, and a long thread:
    # both sides of the split are competing for room, at production constants.
    huge = "\n\n".join(f"## Section {i}\n{'Osmosis detail. ' * 60}" for i in range(40))
    with db_factory() as db:
        topic_id = _seed_topic(db, notes=huge)

    session_id = client.post(
        "/api/chat", json={"message": "C" * 4000, "topic_id": topic_id}
    ).json()["session_id"]
    for _ in range(4):
        client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "message": "C" * 4000,
                "topic_id": topic_id,
            },
        )

    prompt = fake_provider.last_prompt
    assert prompt is not None
    reference = prompt[prompt.index("\n# Reference topic") : prompt.index("\n# Conversation")]
    transcript = prompt.split("\n# Conversation\n", 1)[1]
    # Retrieval stayed inside its share, and material + history together stayed
    # inside the ceiling: a pinned topic can never inflate the prompt.
    assert len(reference) <= retrieval.CONTEXT_MAX_CHARS + 500  # + the framing
    assert len(reference) + len(transcript) <= chatsvc.MAX_HISTORY_CHARS


def test_history_shrinks_to_make_room_for_the_extract(
    client: TestClient,
    fake_provider: MockProvider,
    db_factory: sessionmaker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with db_factory() as db:
        topic_id = _seed_topic(db)
    # A 700-char envelope with a 400-char floor: the extract must push the
    # oldest turn out rather than push the prompt over the ceiling.
    monkeypatch.setattr(chatsvc, "MAX_HISTORY_CHARS", 700)
    monkeypatch.setattr(chatsvc, "MIN_HISTORY_CHARS", 400)

    session_id = client.post(
        "/api/chat", json={"message": "A" * 300, "topic_id": topic_id}
    ).json()["session_id"]
    client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "B" * 300, "topic_id": topic_id},
    )

    prompt = fake_provider.last_prompt
    assert prompt is not None
    assert "B" * 300 in prompt  # the newest turn always survives
    assert "A" * 300 not in prompt  # the oldest gave way to the material
    assert "# Reference topic" in prompt
