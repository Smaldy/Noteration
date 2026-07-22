"""On-demand 'generate more' (MCQs / flashcards) — service + parsing + HTTP."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models import MCQ, Chapter, Document, Flashcard, Subject, Topic
from backend.models.enums import DocumentMode
from backend.services import topics as topicsvc
from backend.services.pipeline.generation import (
    _ASSESSMENT_RULES,
    GenerationParseError,
    build_generation_prompt,
    build_more_flashcards_prompt,
    build_more_mcqs_prompt,
    parse_more_flashcards,
    parse_more_mcqs,
)
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall

_MCQS = json.dumps(
    {
        "mcqs": [
            {
                "question": "What is torque?",
                "options": ["r×F", "m·a", "½mv²"],
                "correct_index": 0,
                "explanation": "Torque is the moment of force, r×F.",
            },
            {
                "question": "Units of angular momentum?",
                "options": ["kg·m²/s", "N", "J"],
                "correct_index": 0,
                "explanation": "L = Iω has units kg·m²/s.",
            },
        ]
    }
)
_FLASHCARDS = json.dumps(
    {"flashcards": [{"front": "Define torque", "back": "Moment of force, r×F."}]}
)


def _seed_topic(session: Session, tmp_path) -> Topic:
    md = tmp_path / "doc.md"
    md.write_text("# Rolling\n\nTorque is r cross F.\n", encoding="utf-8")
    subject = Subject(name="Physics")
    document = Document(
        subject=subject, filename="f.pdf", file_hash="h", markdown_path=str(md)
    )
    chapter = Chapter(document=document, subject=subject, title="Mechanics")
    topic = Topic(chapter=chapter, title="Rolling")
    session.add_all([subject, document, chapter, topic])
    session.commit()
    return topic


# --- parsing ----------------------------------------------------------------


def test_parse_more_mcqs_valid() -> None:
    mcqs = parse_more_mcqs(_MCQS)
    assert len(mcqs) == 2
    assert mcqs[0].correct_index == 0


def test_parse_more_flashcards_valid() -> None:
    cards = parse_more_flashcards(_FLASHCARDS)
    assert len(cards) == 1 and cards[0].front == "Define torque"


def test_parse_more_mcqs_rejects_empty() -> None:
    with pytest.raises(GenerationParseError):
        parse_more_mcqs(json.dumps({"mcqs": []}))


def test_more_mcqs_prompt_lists_existing() -> None:
    prompt = build_more_mcqs_prompt("Rolling", "src", ["What is torque?"])
    assert "do NOT repeat" in prompt
    assert "What is torque?" in prompt


def test_more_mcqs_prompt_includes_language_directive() -> None:
    assert "Output language" not in build_more_mcqs_prompt("Rolling", "src", [])
    es = build_more_mcqs_prompt("Rolling", "src", [], language="es")
    assert "Spanish" in es


def test_every_assessment_prompt_carries_the_shared_rules() -> None:
    """The "generate more" prompts once omitted the math rule.

    Cards added later then rendered `10^3` as literal text while the same cards
    from the first generation typeset fine. Pin all four builders that emit MCQs
    or flashcards, so a new one can't quietly drop the shared rules again.
    """
    prompts = [
        build_generation_prompt("Rolling", "src"),
        build_generation_prompt("Rolling", "src", mode=DocumentMode.exam),
        build_more_mcqs_prompt("Rolling", "src", []),
        build_more_flashcards_prompt("Rolling", "src", []),
    ]
    for prompt in prompts:
        assert _ASSESSMENT_RULES in prompt


# --- service ----------------------------------------------------------------


def test_generate_more_mcqs_appends(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path)
    session.add(MCQ(topic_id=topic.id, question="old?", options=["a", "b"]))
    session.commit()

    waterfall = Waterfall([MockProvider("gemini_free", text=_MCQS)])
    added = topicsvc.generate_more(session, topic.id, "mcqs", waterfall=waterfall)

    assert added == 2
    # appended, not replaced — the original MCQ is still present.
    assert session.query(MCQ).filter_by(topic_id=topic.id).count() == 3
    assert session.query(Flashcard).filter_by(topic_id=topic.id).count() == 0


def test_generate_more_flashcards_appends(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path)
    waterfall = Waterfall([MockProvider("gemini_free", text=_FLASHCARDS)])
    added = topicsvc.generate_more(session, topic.id, "flashcards", waterfall=waterfall)

    assert added == 1
    cards = session.query(Flashcard).filter_by(topic_id=topic.id).all()
    assert len(cards) == 1 and cards[0].ease_factor == 2.5  # SM-2 defaults
    assert session.query(MCQ).filter_by(topic_id=topic.id).count() == 0


def test_generate_more_unknown_topic_raises(session: Session) -> None:
    waterfall = Waterfall([MockProvider("gemini_free", text=_MCQS)])
    with pytest.raises(topicsvc.TopicNotFoundError):
        topicsvc.generate_more(session, 999, "mcqs", waterfall=waterfall)


def test_generate_more_malformed_raises(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path)
    waterfall = Waterfall([MockProvider("gemini_free", text="not json")])
    with pytest.raises(GenerationParseError):
        topicsvc.generate_more(session, topic.id, "mcqs", waterfall=waterfall)
    assert session.query(MCQ).count() == 0  # nothing written


# --- HTTP -------------------------------------------------------------------


def test_http_generate_more_404(client: TestClient) -> None:
    resp = client.post("/api/topics/999/generate", json={"kind": "mcqs"})
    assert resp.status_code == 404


def test_http_generate_more_bad_kind_422(client: TestClient) -> None:
    resp = client.post("/api/topics/1/generate", json={"kind": "notes"})
    assert resp.status_code == 422
