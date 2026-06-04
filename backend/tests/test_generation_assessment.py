"""Generation parsing tests: parse_generation + the consolidated processor.

The notes and assessment are produced by a single model call returning one JSON
object ({notes_md, mcqs, flashcards}); these cover parsing/validation of that
object and the StageProcessor's all-or-nothing write through the real queue.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Flashcard, MCQ, Note, Subject, Topic
from backend.models.enums import DocumentMode, QueueStage, QueueState
from backend.models.processing import QueueJob
from backend.services.pipeline.generation import (
    GenerationParseError,
    build_generation_prompt,
    make_generation_processor,
    parse_generation,
)
from backend.services.queue import JobOutcome, QueueService
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall

_VALID = {
    "notes_md": "# Kinematics\n\nVelocity is dx/dt.",
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
    data = parse_generation(_valid_json())
    assert data.notes_md.startswith("# Kinematics")
    assert len(data.mcqs) == 1
    assert data.mcqs[0].correct_index == 0
    assert data.mcqs[0].options[0] == "rate of position change"
    assert data.flashcards[0].front == "Define acceleration"


def test_parse_tolerates_fences_and_prose() -> None:
    wrapped = f"Here you go:\n```json\n{_valid_json()}\n```\nThanks!"
    data = parse_generation(wrapped)
    assert len(data.mcqs) == 1 and len(data.flashcards) == 1


def test_parse_rejects_non_json() -> None:
    with pytest.raises(GenerationParseError):
        parse_generation("I could not generate questions.")


def test_parse_rejects_missing_notes() -> None:
    bad = json.loads(_valid_json())
    del bad["notes_md"]
    with pytest.raises(GenerationParseError):
        parse_generation(json.dumps(bad))


def test_parse_rejects_correct_index_out_of_range() -> None:
    bad = json.loads(_valid_json())
    bad["mcqs"][0]["correct_index"] = 9
    with pytest.raises(GenerationParseError):
        parse_generation(json.dumps(bad))


def test_parse_rejects_too_few_options() -> None:
    bad = json.loads(_valid_json())
    bad["mcqs"][0]["options"] = ["only one"]
    with pytest.raises(GenerationParseError):
        parse_generation(json.dumps(bad))


def test_parse_rejects_empty_lists() -> None:
    with pytest.raises(GenerationParseError):
        parse_generation(json.dumps({"notes_md": "x", "mcqs": [], "flashcards": []}))


def test_parse_rejects_non_list_fields() -> None:
    # Present-but-not-a-list must raise GenerationParseError, not a bare TypeError.
    with pytest.raises(GenerationParseError):
        parse_generation(json.dumps({"notes_md": "x", "mcqs": None, "flashcards": None}))
    with pytest.raises(GenerationParseError):
        parse_generation(
            json.dumps({"notes_md": "x", "mcqs": {"q": "x"}, "flashcards": []})
        )


def test_parse_rejects_bool_correct_index() -> None:
    bad = json.loads(_valid_json())
    bad["mcqs"][0]["correct_index"] = True  # bool is not a valid index
    with pytest.raises(GenerationParseError):
        parse_generation(json.dumps(bad))


def test_build_generation_prompt_includes_source() -> None:
    prompt = build_generation_prompt("Kinematics", "Velocity = dx/dt")
    assert "Kinematics" in prompt
    assert "Velocity = dx/dt" in prompt
    assert "JSON" in prompt


# --- the StageProcessor via the real queue ----------------------------------


def _seed_topic(
    session: Session, tmp_path, *, mode: DocumentMode = DocumentMode.study
) -> Topic:
    md = tmp_path / "doc.md"
    md.write_text("# Kinematics\n\nVelocity is dx/dt.\n", encoding="utf-8")
    subject = Subject(name="Physics")
    document = Document(
        subject=subject,
        filename="f.pdf",
        file_hash="h",
        markdown_path=str(md),
        mode=mode,
    )
    chapter = Chapter(document=document, subject=subject, title="Ch")
    topic = Topic(chapter=chapter, title="Kinematics")
    session.add_all([subject, document, chapter, topic])
    session.commit()
    return topic


def _gen_job(session: Session, topic: Topic) -> QueueJob:
    job = QueueJob(
        topic_id=topic.id, subject_id=topic.chapter.subject_id, stage=QueueStage.notes
    )
    session.add(job)
    session.commit()
    return job


def test_processor_writes_notes_mcqs_and_flashcards(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path)
    job = _gen_job(session, topic)
    queue = QueueService(session)
    provider = MockProvider("gemini_free", text=_valid_json())
    processor = make_generation_processor(Waterfall([provider]))

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    assert provider.generate_calls == 1  # single consolidated call
    note = session.query(Note).filter_by(topic_id=topic.id).one()
    assert note.content_md.startswith("# Kinematics")
    mcqs = session.query(MCQ).filter_by(topic_id=topic.id).all()
    cards = session.query(Flashcard).filter_by(topic_id=topic.id).all()
    assert len(mcqs) == 1 and len(cards) == 1
    assert mcqs[0].options == ["rate of position change", "mass times accel", "force"]
    # flashcards initialized with SM-2 defaults
    assert cards[0].ease_factor == 2.5
    assert cards[0].interval == 0
    assert cards[0].repetitions == 0
    assert cards[0].due_date is None


def test_processor_malformed_output_rolls_back(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path)
    job = _gen_job(session, topic)
    queue = QueueService(session)
    provider = MockProvider("gemini_free", text="sorry, no JSON here")
    processor = make_generation_processor(Waterfall([provider]))

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.deferred_retry  # transient failure, attempts=1
    assert session.query(Note).count() == 0
    assert session.query(MCQ).count() == 0
    assert session.query(Flashcard).count() == 0
    refreshed = session.get(QueueJob, job.id)
    assert refreshed.attempts == 1
    assert refreshed.state is QueueState.pending


# --- exam mode (assessment-only) --------------------------------------------

_EXAM_JSON = json.dumps(
    {
        "mcqs": [
            {
                "question": "What is velocity?",
                "options": ["rate of position change", "force"],
                "correct_index": 0,
                "explanation": "v = dx/dt.",
            }
        ],
        "flashcards": [{"front": "Define acceleration", "back": "dv/dt."}],
    }
)


def test_build_exam_prompt_drops_notes() -> None:
    prompt = build_generation_prompt(
        "Kinematics", "Velocity = dx/dt", mode=DocumentMode.exam
    )
    assert "notes_md" not in prompt
    assert "flashcards" in prompt and "mcqs" in prompt


def test_parse_generation_allows_missing_notes_in_exam() -> None:
    data = parse_generation(_EXAM_JSON, require_notes=False)
    assert data.notes_md == ""
    assert len(data.mcqs) == 1 and len(data.flashcards) == 1


def test_exam_processor_writes_no_note(session: Session, tmp_path) -> None:
    topic = _seed_topic(session, tmp_path, mode=DocumentMode.exam)
    job = _gen_job(session, topic)
    queue = QueueService(session)
    provider = MockProvider("gemini_free", text=_EXAM_JSON)
    processor = make_generation_processor(Waterfall([provider]))

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    assert provider.generate_calls == 1
    # Exam mode is assessment-only: MCQs + flashcards, but no Note row.
    assert session.query(Note).filter_by(topic_id=topic.id).count() == 0
    assert session.query(MCQ).filter_by(topic_id=topic.id).count() == 1
    assert session.query(Flashcard).filter_by(topic_id=topic.id).count() == 1
