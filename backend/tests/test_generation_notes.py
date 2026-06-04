"""Generation tests: source slicing + the consolidated generation StageProcessor."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Flashcard, MCQ, Note, Subject, Topic
from backend.models.enums import QueueStage, QueueState
from backend.models.processing import QueueJob
from backend.services.pipeline.generation import (
    GENERATION_SCHEMA,
    TopicSourceUnavailableError,
    build_generation_prompt,
    load_topic_source,
    make_generation_processor,
    slice_section,
)
from backend.services.queue import JobOutcome, QueueService
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall

_GEN_JSON = json.dumps(
    {
        "notes_md": "# Notes\n\nDense notes here.",
        "mcqs": [
            {
                "question": "What is velocity?",
                "options": ["dx/dt", "ma"],
                "correct_index": 0,
                "explanation": "rate of position change",
            }
        ],
        "flashcards": [{"front": "acceleration?", "back": "dv/dt"}],
    }
)

_MD = """# Chapter A

intro to A

## Kinematics

Velocity is the rate of change of position.
Acceleration is the rate of change of velocity.

## Dynamics

Newton's laws.

# Chapter B

## Thermo

Heat flows.
"""


# --- source slicing ---------------------------------------------------------


def test_slice_section_returns_topic_body_until_sibling() -> None:
    section = slice_section(_MD, "Kinematics")
    assert section is not None
    assert section.startswith("## Kinematics")
    assert "Velocity is the rate of change" in section
    assert "Newton's laws" not in section  # stops at the next ## sibling


def test_slice_section_chapter_includes_subtopics() -> None:
    section = slice_section(_MD, "Chapter A")
    assert "## Kinematics" in section
    assert "## Dynamics" in section
    assert "# Chapter B" not in section  # stops at the next top-level heading


def test_slice_section_no_match_returns_none() -> None:
    assert slice_section(_MD, "Nonexistent") is None


def test_slice_section_is_case_insensitive() -> None:
    assert slice_section(_MD, "kinEMATICS") is not None


# --- load_topic_source fallbacks --------------------------------------------


def _seed(session: Session, tmp_path: Path, *, topic_title: str) -> Topic:
    md = tmp_path / "doc.md"
    md.write_text(_MD, encoding="utf-8")
    subject = Subject(name="Physics")
    document = Document(
        subject=subject, filename="f.pdf", file_hash="h", markdown_path=str(md)
    )
    chapter = Chapter(document=document, subject=subject, title="Chapter A")
    topic = Topic(chapter=chapter, title=topic_title)
    session.add_all([subject, document, chapter, topic])
    session.commit()
    return topic


def test_load_topic_source_matches_topic(session: Session, tmp_path: Path) -> None:
    topic = _seed(session, tmp_path, topic_title="Kinematics")
    source = load_topic_source(session, topic)
    assert "Velocity is the rate of change" in source
    assert "Newton's laws" not in source


def test_load_topic_source_falls_back_to_chapter(session: Session, tmp_path: Path) -> None:
    # Topic title doesn't match any heading → use the chapter section.
    topic = _seed(session, tmp_path, topic_title="Renamed Topic")
    source = load_topic_source(session, topic)
    assert "## Kinematics" in source and "## Dynamics" in source


_HEADINGLESS_MD = "\n\n".join(f"Paragraph {i} content about physics." * 40 for i in range(12))


def _seed_headingless(session: Session, tmp_path: Path, titles: list[str]) -> list[Topic]:
    """A document whose markdown has no headings + topics named off-content."""
    md = tmp_path / "headingless.md"
    md.write_text(_HEADINGLESS_MD, encoding="utf-8")
    subject = Subject(name="Physics")
    document = Document(
        subject=subject, filename="f.pdf", file_hash="h2", markdown_path=str(md)
    )
    chapter = Chapter(document=document, subject=subject, title="Fundamentals Physics")
    topics = [
        Topic(chapter=chapter, title=title, order_index=i)
        for i, title in enumerate(titles)
    ]
    session.add_all([subject, document, chapter, *topics])
    session.commit()
    return topics


def test_headingless_doc_does_not_send_whole_document_per_topic(
    session: Session, tmp_path: Path
) -> None:
    # The bug: with no headings and content-named topics, every topic fell back
    # to the WHOLE document, re-sending the full file N times and burning quota.
    titles = ["Torque", "Angular momentum", "Rolling", "Gyroscopes"]
    topics = _seed_headingless(session, tmp_path, titles)
    full = (tmp_path / "headingless.md").read_text(encoding="utf-8")

    sources = [load_topic_source(session, t) for t in topics]

    # Each topic gets a bounded slice, not the entire document.
    for src in sources:
        assert len(src) < len(full)
        assert len(src) <= 8000  # SOURCE_MAX_CHARS
    # Topics get *different* slices (proportional by reading order), so the doc
    # is covered once across topics instead of re-sent in full per topic.
    assert len(set(sources)) == len(sources)


def test_load_topic_source_is_capped(session: Session, tmp_path: Path) -> None:
    # Even a single-topic headingless doc is hard-capped (safety net).
    [topic] = _seed_headingless(session, tmp_path, ["Only topic"])
    source = load_topic_source(session, topic)
    assert len(source) <= 8000


def test_load_topic_source_missing_markdown_raises(session: Session, tmp_path: Path) -> None:
    topic = _seed(session, tmp_path, topic_title="Kinematics")
    chapter = session.get(Chapter, topic.chapter_id)
    document = session.get(Document, chapter.document_id)
    document.markdown_path = str(tmp_path / "gone.md")
    session.commit()
    with pytest.raises(TopicSourceUnavailableError):
        load_topic_source(session, topic)


# --- prompt -----------------------------------------------------------------


def test_build_generation_prompt_includes_title_and_source() -> None:
    prompt = build_generation_prompt("Kinematics", "Velocity is rate of change.")
    assert "Kinematics" in prompt
    assert "Velocity is rate of change." in prompt
    assert "JSON" in prompt  # asks for one combined JSON object
    assert "flashcards" in prompt


# --- the consolidated StageProcessor via the real queue ---------------------


def _gen_job(session: Session, tmp_path: Path) -> tuple[QueueService, QueueJob]:
    topic = _seed(session, tmp_path, topic_title="Kinematics")
    job = QueueJob(
        topic_id=topic.id, subject_id=topic.chapter.subject_id, stage=QueueStage.notes
    )
    session.add(job)
    session.commit()
    return QueueService(session), job


def test_generation_processor_writes_note_and_assessment_in_one_call(
    session: Session, tmp_path: Path
) -> None:
    queue, job = _gen_job(session, tmp_path)
    provider = MockProvider("gemini_free", text=_GEN_JSON)
    processor = make_generation_processor(Waterfall([provider]))

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    # ONE call produced both notes and the assessment — no second round trip.
    assert provider.generate_calls == 1
    assert provider.last_response_schema is GENERATION_SCHEMA  # structured output
    note = session.query(Note).filter_by(topic_id=job.topic_id).one()
    assert note.content_md == "# Notes\n\nDense notes here."
    assert note.is_manual is False
    assert session.query(MCQ).filter_by(topic_id=job.topic_id).count() == 1
    assert session.query(Flashcard).filter_by(topic_id=job.topic_id).count() == 1
    refreshed = session.get(QueueJob, job.id)
    assert refreshed.state is QueueState.done
    assert refreshed.assigned_provider == "gemini_free"


def test_generation_processor_exhaustion_writes_nothing(
    session: Session, tmp_path: Path
) -> None:
    queue, job = _gen_job(session, tmp_path)
    # No headroom anywhere → waterfall raises AllProvidersExhausted.
    provider = MockProvider("gemini_free", available=False, headroom=0)
    processor = make_generation_processor(Waterfall([provider]))

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.exhausted
    assert session.query(Note).filter_by(topic_id=job.topic_id).count() == 0
    assert session.query(MCQ).count() == 0
    refreshed = session.get(QueueJob, job.id)
    assert refreshed.state is QueueState.pending  # deferred, not failed
