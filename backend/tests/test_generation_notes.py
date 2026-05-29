"""Notes generation tests (Phase 7a): source slicing + the notes StageProcessor."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Note, Subject, Topic
from backend.models.enums import QueueStage, QueueState
from backend.models.processing import QueueJob
from backend.services.pipeline.generation import (
    TopicSourceUnavailableError,
    build_notes_prompt,
    load_topic_source,
    make_notes_processor,
    slice_section,
)
from backend.services.queue import JobOutcome, QueueService
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall

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


def test_load_topic_source_missing_markdown_raises(session: Session, tmp_path: Path) -> None:
    topic = _seed(session, tmp_path, topic_title="Kinematics")
    chapter = session.get(Chapter, topic.chapter_id)
    document = session.get(Document, chapter.document_id)
    document.markdown_path = str(tmp_path / "gone.md")
    session.commit()
    with pytest.raises(TopicSourceUnavailableError):
        load_topic_source(session, topic)


# --- prompt -----------------------------------------------------------------


def test_build_notes_prompt_includes_title_and_source() -> None:
    prompt = build_notes_prompt("Kinematics", "Velocity is rate of change.")
    assert "Kinematics" in prompt
    assert "Velocity is rate of change." in prompt
    assert "Markdown" in prompt


# --- the StageProcessor via the real queue ----------------------------------


def _notes_job(session: Session, tmp_path: Path) -> tuple[QueueService, QueueJob]:
    topic = _seed(session, tmp_path, topic_title="Kinematics")
    job = QueueJob(topic_id=topic.id, stage=QueueStage.notes)
    session.add(job)
    session.commit()
    return QueueService(session), job


def test_notes_processor_writes_note_and_commits(session: Session, tmp_path: Path) -> None:
    queue, job = _notes_job(session, tmp_path)
    provider = MockProvider("gemini_free", text="# Notes\n\nDense notes here.")
    processor = make_notes_processor(Waterfall([provider]))

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    assert provider.generate_calls == 1
    note = session.query(Note).filter_by(topic_id=job.topic_id).one()
    assert note.content_md == "# Notes\n\nDense notes here."
    assert note.is_manual is False
    refreshed = session.get(QueueJob, job.id)
    assert refreshed.state is QueueState.done
    assert refreshed.assigned_provider == "gemini_free"


def test_notes_processor_exhaustion_writes_nothing(session: Session, tmp_path: Path) -> None:
    queue, job = _notes_job(session, tmp_path)
    # No headroom anywhere → waterfall raises AllProvidersExhausted.
    provider = MockProvider("gemini_free", available=False, headroom=0)
    processor = make_notes_processor(Waterfall([provider]))

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.exhausted
    assert session.query(Note).filter_by(topic_id=job.topic_id).count() == 0
    refreshed = session.get(QueueJob, job.id)
    assert refreshed.state is QueueState.pending  # deferred, not failed
