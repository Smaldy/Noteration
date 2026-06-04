"""Formula stage tests: detection, cropping, registration, lazy transcription.

The background queue only *registers* equation regions (``pending`` formulas, no
vision call); transcription is deferred to the on-demand
``transcribe_pending_formulas`` path. These cover both halves.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Formula, Note, Subject, Topic
from backend.models.enums import FormulaState, QueueStage
from backend.models.processing import QueueJob
from backend.services.pipeline.formula import (
    MathRegion,
    NO_OP_PROVIDER,
    crop_pdf_region,
    detect_math_regions,
    make_formula_processor,
    transcribe_pending_formulas,
)
from backend.services.queue import JobOutcome, QueueService
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall


# --- detection --------------------------------------------------------------


def test_detect_display_inline_and_env() -> None:
    text = (
        r"Energy $$E=mc^2$$ and inline $a^2+b^2$ plus \[x=1\] and \(y=2\) "
        r"and \begin{equation}F=ma\end{equation}"
    )
    found = [r.text for r in detect_math_regions(text)]
    assert "E=mc^2" in found
    assert "a^2+b^2" in found
    assert "x=1" in found
    assert "y=2" in found
    assert "F=ma" in found


def test_detect_dedupes() -> None:
    found = detect_math_regions("$x$ and again $x$ and $$x$$")
    assert [r.text for r in found] == ["x"]


def test_detect_no_math() -> None:
    assert detect_math_regions("plain prose, costs $5 only") == []


# --- real crop over a generated PDF -----------------------------------------


def test_crop_pdf_region_finds_text(tmp_path: Path) -> None:
    fitz = __import__("fitz")
    pdf = tmp_path / "doc.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "F = ma is Newton's second law")
    doc.save(str(pdf))
    doc.close()

    found = crop_pdf_region(pdf, "F = ma")
    assert found is not None
    image, bbox = found
    assert image[:4] == b"\x89PNG"
    assert bbox["page"] == 0

    assert crop_pdf_region(pdf, "not present anywhere") is None


# --- processor via the queue ------------------------------------------------


def _seed_topic(session: Session) -> Topic:
    subject = Subject(name="Physics")
    document = Document(subject=subject, filename="f.pdf", file_hash="h")
    chapter = Chapter(document=document, subject=subject, title="Ch")
    topic = Topic(chapter=chapter, title="Mechanics")
    session.add_all([subject, document, chapter, topic])
    session.commit()
    return topic


def _job(session: Session, topic: Topic) -> QueueJob:
    job = QueueJob(
        topic_id=topic.id, subject_id=topic.chapter.subject_id, stage=QueueStage.formula
    )
    session.add(job)
    session.commit()
    return job


def _fake_locator(_session, _topic, region: MathRegion) -> dict:
    region.bbox = {"page": 0, "x0": 0, "y0": 0, "x1": 10, "y1": 10}
    return region.bbox


# --- registration stage (no vision call) ------------------------------------


def test_formula_processor_registers_pending_formula(session: Session) -> None:
    topic = _seed_topic(session)
    job = _job(session, topic)
    queue = QueueService(session)
    processor = make_formula_processor(
        source_loader=lambda _s, _t: "$$F=ma$$",
        locator=_fake_locator,
    )

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    note = session.query(Note).filter_by(topic_id=topic.id).one()
    formula = session.query(Formula).filter_by(note_id=note.id).one()
    # Registered, NOT transcribed — vision is deferred to the on-demand endpoint.
    assert formula.state is FormulaState.pending
    assert formula.latex == ""
    assert formula.bbox["page"] == 0
    # The registration stage makes no model call.
    assert session.get(QueueJob, job.id).assigned_provider == NO_OP_PROVIDER


def test_formula_processor_no_math_is_noop(session: Session) -> None:
    topic = _seed_topic(session)
    job = _job(session, topic)
    queue = QueueService(session)
    processor = make_formula_processor(
        source_loader=lambda _s, _t: "no math here",
        locator=_fake_locator,
    )

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    assert session.query(Note).count() == 0
    assert session.query(Formula).count() == 0
    assert session.get(QueueJob, job.id).assigned_provider == NO_OP_PROVIDER


def test_formula_processor_skips_unlocatable_regions(session: Session) -> None:
    topic = _seed_topic(session)
    job = _job(session, topic)
    queue = QueueService(session)
    processor = make_formula_processor(
        source_loader=lambda _s, _t: "$$F=ma$$",
        locator=lambda _s, _t, _r: None,  # cannot locate
    )

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    assert session.query(Formula).count() == 0
    assert session.get(QueueJob, job.id).assigned_provider == NO_OP_PROVIDER


# --- on-demand (lazy) transcription -----------------------------------------


def test_transcribe_pending_formulas_fills_latex(session: Session) -> None:
    # Register a pending formula via the stage, then transcribe it on demand.
    topic = _seed_topic(session)
    job = _job(session, topic)
    queue = QueueService(session)
    queue.process_job(
        job,
        make_formula_processor(
            source_loader=lambda _s, _t: "$$F=ma$$", locator=_fake_locator
        ),
    )
    pending = session.query(Formula).filter_by(state=FormulaState.pending).one()

    vision = MockProvider("gemini_vision", supports_vision=True, text="F = ma")
    transcribed = transcribe_pending_formulas(
        session,
        topic.id,
        Waterfall([vision]),
        cropper=lambda _s, _f: b"\x89PNGfake",
    )

    assert vision.transcribe_calls == 1
    assert [f.id for f in transcribed] == [pending.id]
    session.refresh(pending)
    assert pending.state is FormulaState.reconstructed
    assert pending.latex == "F = ma"


def test_transcribe_pending_formulas_leaves_uncroppable_pending(session: Session) -> None:
    topic = _seed_topic(session)
    job = _job(session, topic)
    queue = QueueService(session)
    queue.process_job(
        job,
        make_formula_processor(
            source_loader=lambda _s, _t: "$$F=ma$$", locator=_fake_locator
        ),
    )

    vision = MockProvider("gemini_vision", supports_vision=True, text="F = ma")
    transcribed = transcribe_pending_formulas(
        session, topic.id, Waterfall([vision]), cropper=lambda _s, _f: None
    )

    assert transcribed == []
    assert vision.transcribe_calls == 0
    assert session.query(Formula).filter_by(state=FormulaState.pending).count() == 1
