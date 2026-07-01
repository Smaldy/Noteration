"""Stage 3 — Formula transcription (vision, scoped, lazily transcribed).

Detection happens in the background queue, but the expensive **vision call is
deferred**: the queue only *detects + registers* equation regions as ``Formula``
rows in state ``pending`` (located on the page, but with no LaTeX yet), attached
to the topic's get-or-created AI ``Note``. No ``transcribe_image`` runs during
background processing — this keeps the per-minute request budget and the rolling
tokens-per-minute ceiling for the consolidated generation call, which is what the
queue actually needs to make a topic studiable.

The actual transcription is triggered **on demand** when a user opens a topic: the
``POST /api/topics/{id}/formulas/transcribe`` endpoint calls
``transcribe_pending_formulas`` over a vision ``Waterfall``, which re-crops each
pending region from the cached PDF (grayscale, 150 DPI — a tight visual-token
footprint) and flips the ``Formula`` to ``reconstructed`` with its LaTeX.

The detector and the region locator/cropper are injected so the processor and the
lazy service are testable without PyMuPDF.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Formula, Note, Topic
from backend.models.enums import FormulaState
from backend.models.processing import QueueJob
from backend.paths import UPLOADS_DIR
from backend.services.pipeline.generation import (
    get_or_create_ai_note,
    load_topic_source,
)
from backend.services.providers.base import ProviderResult
from backend.services.providers.waterfall import Waterfall

# Vision output cap — LaTeX for one equation is short; keep the spend tight.
FORMULA_MAX_TOKENS = 512
# Stamp for a formula stage that did no model call (it never does one now).
NO_OP_PROVIDER = "none"
# On-demand crop render settings (docs/architecture.md "cut input tokens"): grayscale
# at 150 DPI strictly bounds the visual input token footprint of each equation
# crop, protecting the rolling tokens-per-minute ceiling.
CROP_DPI = 150
CROP_PAD = 4.0

# Math delimiters markitdown/source may carry. Display/env first; inline last.
_MATH_PATTERNS = (
    re.compile(r"\$\$(.+?)\$\$", re.DOTALL),
    re.compile(r"\\\[(.+?)\\\]", re.DOTALL),
    re.compile(
        r"\\begin\{(equation|align|gather|multline|math)\*?\}(.+?)"
        r"\\end\{\1\*?\}",
        re.DOTALL,
    ),
    re.compile(r"\\\((.+?)\\\)", re.DOTALL),
    re.compile(r"(?<!\$)\$(?!\$)([^$\n]+?)\$(?!\$)"),  # inline $...$
)


@dataclass
class MathRegion:
    text: str  # the math content (without delimiters)
    bbox: dict[str, Any] | None = None  # filled in once located on a page


# Locator: find a detected region on a PDF page, set + return its bbox (no render).
RegionLocator = Callable[[Session, Topic, MathRegion], "dict[str, Any] | None"]
# On-demand cropper: render a registered Formula's region to PNG bytes (or None).
FormulaCropper = Callable[[Session, Formula], "bytes | None"]
SourceLoader = Callable[[Session, Topic], str]


def detect_math_regions(source_text: str) -> list[MathRegion]:
    """Find delimited math in the source, de-duplicated, in first-seen order."""
    seen: set[str] = set()
    regions: list[MathRegion] = []
    for pattern in _MATH_PATTERNS:
        for match in pattern.finditer(source_text):
            # The env pattern captures the body in group 2; others in group 1.
            body = match.group(match.lastindex)
            text = body.strip()
            if text and text not in seen:
                seen.add(text)
                regions.append(MathRegion(text=text))
    return regions


def locate_pdf_region(
    pdf_path: str | Path, needle: str, *, pad: float = CROP_PAD
) -> dict[str, Any] | None:
    """Find ``needle`` text in the PDF and return its bbox (page + rect), no render.

    Registration only needs *where* the region is; rendering is deferred to the
    on-demand transcription so the background queue does zero vision work.
    """
    import fitz  # PyMuPDF

    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            rects = page.search_for(needle)
            if not rects:
                continue
            rect = rects[0]
            return {
                "page": page.number,
                "x0": rect.x0,
                "y0": rect.y0,
                "x1": rect.x1,
                "y1": rect.y1,
            }
    return None


def crop_pdf_bbox(
    pdf_path: str | Path,
    bbox: dict[str, Any],
    *,
    dpi: int = CROP_DPI,
    pad: float = CROP_PAD,
) -> bytes | None:
    """Render the region described by ``bbox`` to grayscale PNG bytes at ``dpi``.

    Grayscale + 150 DPI keeps the cropped equation image small so its vision
    input-token footprint stays minimal (docs/architecture.md). Returns None if the
    bbox is unusable (missing page/coords).
    """
    import fitz  # PyMuPDF

    try:
        page_no = int(bbox["page"])
        clip = fitz.Rect(
            bbox["x0"] - pad, bbox["y0"] - pad, bbox["x1"] + pad, bbox["y1"] + pad
        )
    except (KeyError, TypeError, ValueError):
        return None
    with fitz.open(str(pdf_path)) as doc:
        if page_no < 0 or page_no >= doc.page_count:
            return None
        page = doc[page_no]
        # csGRAY → single-channel (grayscale) output; far fewer pixels' worth of
        # tokens than a colour render at the old 200 DPI.
        pixmap = page.get_pixmap(dpi=dpi, clip=clip, colorspace=fitz.csGRAY)
        return pixmap.tobytes("png")


def crop_pdf_region(
    pdf_path: str | Path, needle: str, *, dpi: int = CROP_DPI, pad: float = CROP_PAD
) -> tuple[bytes, dict[str, Any]] | None:
    """Locate ``needle`` and return (grayscale PNG bytes, bbox), or None.

    Convenience that locates and renders in one pass (used by tests); the live
    pipeline locates at registration and crops by bbox on demand.
    """
    bbox = locate_pdf_region(pdf_path, needle, pad=pad)
    if bbox is None:
        return None
    image = crop_pdf_bbox(pdf_path, bbox, dpi=dpi, pad=pad)
    if image is None:
        return None
    return image, bbox


def _topic_pdf_path(session: Session, topic: Topic) -> Path | None:
    """The cached original PDF backing ``topic``'s document, if present."""
    chapter = session.get(Chapter, topic.chapter_id)
    document = session.get(Document, chapter.document_id) if chapter else None
    if document is None:
        return None
    pdf_path = UPLOADS_DIR / f"{document.file_hash}.pdf"
    return pdf_path if pdf_path.is_file() else None


def locate_region_in_pdf(
    session: Session, topic: Topic, region: MathRegion
) -> dict[str, Any] | None:
    """Default locator: find the region in the document's cached PDF (bbox only)."""
    pdf_path = _topic_pdf_path(session, topic)
    if pdf_path is None:
        return None
    bbox = locate_pdf_region(pdf_path, region.text)
    if bbox is not None:
        region.bbox = bbox
    return bbox


def make_formula_processor(
    *,
    source_loader: SourceLoader = load_topic_source,
    detector: Callable[[str], list[MathRegion]] = detect_math_regions,
    locator: RegionLocator = locate_region_in_pdf,
) -> Callable[[QueueJob, Session], ProviderResult]:
    """Build the queue ``StageProcessor`` for the formula *registration* stage.

    Detects math regions in the topic's source and registers each locatable one as
    a ``pending`` ``Formula`` (no LaTeX yet) on the topic's AI Note. Makes **no**
    model call — vision is deferred to the on-demand endpoint — so the stage is a
    cheap, budget-free placeholder pass. No math / nothing locatable → no rows.
    """

    def process(job: QueueJob, session: Session) -> ProviderResult:
        topic = session.get(Topic, job.topic_id)
        regions = detector(source_loader(session, topic))
        if not regions:
            return ProviderResult(text="", provider=NO_OP_PROVIDER)  # no math

        note = get_or_create_ai_note(session, topic)
        registered = 0
        for region in regions:
            bbox = locator(session, topic, region)
            if bbox is None:
                continue  # couldn't locate this region; don't register a dead placeholder
            session.add(
                Formula(
                    note_id=note.id,
                    latex="",  # filled on demand
                    state=FormulaState.pending,
                    confidence=None,
                    bbox=bbox,
                )
            )
            registered += 1
        return ProviderResult(
            text=f"registered {registered} formula region(s)", provider=NO_OP_PROVIDER
        )

    return process


# -- on-demand (lazy) vision transcription -----------------------------------


def crop_formula_image(session: Session, formula: Formula) -> bytes | None:
    """Default on-demand cropper: render a pending ``Formula``'s region from PDF."""
    note = session.get(Note, formula.note_id)
    topic = session.get(Topic, note.topic_id) if note else None
    if topic is None or not formula.bbox:
        return None
    pdf_path = _topic_pdf_path(session, topic)
    if pdf_path is None:
        return None
    return crop_pdf_bbox(pdf_path, formula.bbox)


def pending_formulas_for_topic(session: Session, topic_id: int) -> list[Formula]:
    """All ``pending`` formulas on a topic's notes (the lazy-transcribe work list)."""
    return list(
        session.scalars(
            select(Formula)
            .join(Note, Formula.note_id == Note.id)
            .where(Note.topic_id == topic_id, Formula.state == FormulaState.pending)
            .order_by(Formula.id)
        )
    )


def transcribe_pending_formulas(
    session: Session,
    topic_id: int,
    waterfall: Waterfall,
    *,
    cropper: FormulaCropper = crop_formula_image,
    max_tokens: int = FORMULA_MAX_TOKENS,
) -> list[Formula]:
    """Transcribe a topic's pending formulas on demand; commit the results.

    Crops each pending region (grayscale, 150 DPI) and sends it to the vision
    ``Waterfall``; on success the ``Formula`` flips to ``reconstructed`` with its
    LaTeX. A region that can't be cropped is left ``pending`` (retriable later). A
    provider-exhaustion error propagates so the caller (router) can report it —
    any already-transcribed rows in this pass are still committed. Returns the
    formulas that were transcribed this call.
    """
    pending = pending_formulas_for_topic(session, topic_id)
    transcribed: list[Formula] = []
    try:
        for formula in pending:
            image = cropper(session, formula)
            if image is None:
                continue
            result = waterfall.transcribe_image(image, max_tokens=max_tokens)
            formula.latex = result.text.strip()
            formula.state = FormulaState.reconstructed
            transcribed.append(formula)
    finally:
        session.commit()
    return transcribed
