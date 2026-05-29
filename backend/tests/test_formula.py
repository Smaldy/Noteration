"""Formula stage tests (Phase 7c): detection, cropping, processor, integration."""

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
)
from backend.services.pipeline.generation import make_notes_processor
from backend.services.queue import JobOutcome, QueueService
from backend.services.providers.base import BudgetProbe, Provider, ProviderResult
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
    job = QueueJob(topic_id=topic.id, stage=QueueStage.formula)
    session.add(job)
    session.commit()
    return job


def _fake_cropper(_session, _topic, region: MathRegion) -> bytes:
    region.bbox = {"page": 0}
    return b"\x89PNGfake"


def test_formula_processor_stores_reconstructed_formula(session: Session) -> None:
    topic = _seed_topic(session)
    job = _job(session, topic)
    queue = QueueService(session)
    vision = MockProvider("gemini_vision", supports_vision=True, text="F = ma")
    processor = make_formula_processor(
        Waterfall([vision]),
        source_loader=lambda _s, _t: "$$F=ma$$",
        cropper=_fake_cropper,
    )

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    note = session.query(Note).filter_by(topic_id=topic.id).one()
    formula = session.query(Formula).filter_by(note_id=note.id).one()
    assert formula.latex == "F = ma"
    assert formula.state is FormulaState.reconstructed
    assert formula.bbox == {"page": 0}
    assert session.get(QueueJob, job.id).assigned_provider == "gemini_vision"


def test_formula_processor_no_math_is_noop(session: Session) -> None:
    topic = _seed_topic(session)
    job = _job(session, topic)
    queue = QueueService(session)
    vision = MockProvider("gemini_vision", supports_vision=True, text="x")
    processor = make_formula_processor(
        Waterfall([vision]),
        source_loader=lambda _s, _t: "no math here",
        cropper=_fake_cropper,
    )

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    assert vision.transcribe_calls == 0
    assert session.query(Note).count() == 0
    assert session.query(Formula).count() == 0
    assert session.get(QueueJob, job.id).assigned_provider == NO_OP_PROVIDER


def test_formula_processor_skips_unlocatable_regions(session: Session) -> None:
    topic = _seed_topic(session)
    job = _job(session, topic)
    queue = QueueService(session)
    vision = MockProvider("gemini_vision", supports_vision=True, text="F = ma")
    processor = make_formula_processor(
        Waterfall([vision]),
        source_loader=lambda _s, _t: "$$F=ma$$",
        cropper=lambda _s, _t, _r: None,  # cannot locate
    )

    outcome = queue.process_job(job, processor)

    assert outcome is JobOutcome.done
    assert vision.transcribe_calls == 0
    assert session.query(Formula).count() == 0
    assert session.get(QueueJob, job.id).assigned_provider == NO_OP_PROVIDER


# --- formula -> notes integration (shared Note, embedded LaTeX) -------------


class _CapturingProvider(Provider):
    """Records the prompt it was asked to generate, returns fixed text."""

    name = "capture"
    supports_vision = False

    def __init__(self, text: str) -> None:
        self.text = text
        self.last_prompt = ""

    def generate(self, prompt: str, *, max_tokens: int) -> ProviderResult:
        self.last_prompt = prompt
        return ProviderResult(text=self.text, provider=self.name)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        raise NotImplementedError

    def budget_probe(self) -> BudgetProbe:
        return BudgetProbe(True, 100, "none", None, False)


def test_formula_then_notes_share_note_and_embed_latex(session: Session) -> None:
    topic = _seed_topic(session)
    queue = QueueService(session)
    source = "$$F=ma$$"

    # Formula stage: creates the Note + a Formula.
    formula_job = QueueJob(topic_id=topic.id, stage=QueueStage.formula)
    session.add(formula_job)
    session.commit()
    vision = MockProvider("gemini_vision", supports_vision=True, text="F = ma")
    queue.process_job(
        formula_job,
        make_formula_processor(
            Waterfall([vision]), source_loader=lambda _s, _t: source, cropper=_fake_cropper
        ),
    )

    # Notes stage: same Note gets filled, with the LaTeX embedded in the prompt.
    notes_job = QueueJob(topic_id=topic.id, stage=QueueStage.notes)
    session.add(notes_job)
    session.commit()
    capture = _CapturingProvider(text="# Mechanics notes")
    queue.process_job(
        notes_job,
        make_notes_processor(Waterfall([capture]), source_loader=lambda _s, _t: source),
    )

    notes = session.query(Note).filter_by(topic_id=topic.id).all()
    assert len(notes) == 1  # both stages used the same Note
    assert notes[0].content_md == "# Mechanics notes"
    assert "F = ma" in capture.last_prompt  # transcribed LaTeX handed to notes
    assert session.query(Formula).count() == 1
