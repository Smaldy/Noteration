"""Assessment generation tests (Phase 7b): parsing + the assessment processor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Flashcard, MCQ, Note, Subject, Topic
from backend.models.enums import QueueStage, QueueState
from backend.models.processing import QueueJob
from backend.services.pipeline.generation import (
    AssessmentParseError,
    NotesContextMissingError,
    build_assessment_prompt,
    make_assessment_processor,
    parse_assessment,
)
from backend.services.queue import JobOutcome, QueueService
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall

_VALID = {
    "mcqs": [
        {
            "question": "What is velocity?",
            "options": ["rate of position change", "mass times accel", "force"],
            "correct_index": 0,
            "explanation": "v = dx/dt.",
        }
    ],
    "flashcards": [
        {"front": "Define acceleration", "back": "Rate of change of velocity."}
    ],
}


def _valid_json() -> str:
    return json.dumps(_VALID)


# --- parsing ----------------------------------------------------------------


def test_parse_valid_json() -> None:
    data = parse_assessment(_valid_json())
    assert len(data.mcqs) == 1
    assert data.mcqs[0].correct_index == 0
    assert data.mcqs[0].options[0] == "rate of position change"
    assert data.flashcards[0].front == "Define acceleration"


def test_parse_tolerates_fences_and_prose() -> None:
    wrapped = f"Here you go:\n```json\n{_valid_json()}\n```\nThanks!"
    data = parse_assessment(wrapped)
    assert len(data.mcqs) == 1 and len(data.flashcards) == 1


def test_parse_rejects_non_json() -> None:
    with pytest.raises(AssessmentParseError):
        parse_assessment("I could not generate questions.")


def test_parse_rejects_correct_index_out_of_range() -> None:
    bad = json.loads(_valid_json())
    bad["mcqs"][0]["correct_index"] = 9
    with pytest.raises(AssessmentParseError):
        parse_assessment(json.dumps(bad))


def test_parse_rejects_too_few_options() -> None:
    bad = json.loads(_valid_json())
    bad["mcqs"][0]["options"] = ["only one"]
    with pytest.raises(AssessmentParseError):
        parse_assessment(json.dumps(bad))


def test_parse_rejects_empty_lists() -> None:
    with pytest.raises(AssessmentParseError):
        parse_assessment(json.dumps({"mcqs": [], "flashcards": []}))


def test_parse_rejects_bool_correct_index() -> None:
    bad = json.loads(_valid_json())
    bad["mcqs"][0]["correct_index"] = True  # bool is not a valid index
    with pytest.raises(AssessmentParseError):
        parse_assessment(json.dumps(bad))


def test_build_assessment_prompt_includes_notes() -> None:
    prompt = build_assessment_prompt("Kinematics", "Velocity = dx/dt")
    assert "Kinematics" in prompt
    assert "Velocity = dx/dt" in prompt
    assert "JSON" in prompt


# --- the StageProcessor via the real queue ----------------------------------


def _seed_topic_with_notes(session: Session, *, with_notes: bool = True) -> Topic:
    subject = Subject(name="Physics")
    document = Document(subject=subject, filename="f.pdf", file_hash="h")
    chapter = Chapter(document=document, subject=subject, title="Ch")
    topic = Topic(chapter=chapter, title="Kinematics")
    session.add_all([subject, document, chapter, topic])
    session.commit()
    if with_notes:
        session.add(Note(topic_id=topic.id, content_md="Velocity = dx/dt", is_manual=False))
        session.commit()
    return topic


def _assessment_job(session: Session, topic: Topic) -> QueueJob:
    job = QueueJob(topic_id=topic.id, stage=QueueStage.assessment)
    session.add(job)
    session.commit()
    return job


def test_assessment_processor_writes_mcqs_and_flashcards(session: Session) -> None:
    topic = _seed_topic_with_notes(session)
    job = _assessment_job(session, topic)
    queue = QueueService(session)
    provider = MockProvider("gemini_free", text=_valid_json())
    processor = make_assessment_processor(Waterfall([provider]))

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    mcqs = session.query(MCQ).filter_by(topic_id=topic.id).all()
    cards = session.query(Flashcard).filter_by(topic_id=topic.id).all()
    assert len(mcqs) == 1 and len(cards) == 1
    assert mcqs[0].options == ["rate of position change", "mass times accel", "force"]
    # flashcards initialized with SM-2 defaults
    assert cards[0].ease_factor == 2.5
    assert cards[0].interval == 0
    assert cards[0].repetitions == 0
    assert cards[0].due_date is None


def test_assessment_without_notes_fails_and_writes_nothing(session: Session) -> None:
    topic = _seed_topic_with_notes(session, with_notes=False)
    job = _assessment_job(session, topic)
    queue = QueueService(session)
    provider = MockProvider("gemini_free", text=_valid_json())
    processor = make_assessment_processor(Waterfall([provider]))

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.deferred_retry  # transient failure, attempts=1
    assert session.query(MCQ).count() == 0
    assert session.query(Flashcard).count() == 0


def test_assessment_malformed_output_rolls_back(session: Session) -> None:
    topic = _seed_topic_with_notes(session)
    job = _assessment_job(session, topic)
    queue = QueueService(session)
    provider = MockProvider("gemini_free", text="sorry, no JSON here")
    processor = make_assessment_processor(Waterfall([provider]))

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.deferred_retry
    assert session.query(MCQ).count() == 0
    assert session.query(Flashcard).count() == 0
    refreshed = session.get(QueueJob, job.id)
    assert refreshed.attempts == 1
    assert refreshed.state is QueueState.pending
