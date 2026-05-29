"""Stage 3 — Formula transcription (vision, scoped). Sub-wave 7c.

Detect-then-crop on the cheapest tier (docs/ai-pipeline.md, the locked strategy;
the concrete detector was "Still open" in docs/review.md — we take the cheapest
option: a delimiter heuristic over the topic's source markdown). For each detected
math region we locate it in the source PDF, crop the region, and transcribe it to
LaTeX via the vision ``Waterfall``. Each transcription is stored as a ``Formula``
in state ``reconstructed`` (low/None confidence surfaces first in review),
attached to the topic's get-or-created AI ``Note`` so the later notes stage embeds
the cleaned LaTeX.

Runs before notes (queue STAGE_ORDER) and, via priority ordering, exam-critical
topics first — so scarce vision budget is spent where it matters most.

The detector and region cropper are injected so the processor is testable without
PyMuPDF; the default cropper uses the cached source PDF.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Formula, Topic
from backend.models.enums import FormulaState
from backend.models.processing import QueueJob
from backend.services.documents import UPLOADS_DIR
from backend.services.pipeline.generation import get_or_create_ai_note, load_topic_source
from backend.services.providers.base import ProviderResult
from backend.services.providers.waterfall import Waterfall

# Vision output cap — LaTeX for one equation is short; keep the spend tight.
FORMULA_MAX_TOKENS = 512
# Stamp for a formula stage that did no model call (topic has no math).
NO_OP_PROVIDER = "none"

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


RegionCropper = Callable[[Session, Topic, MathRegion], "bytes | None"]
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


def crop_pdf_region(
    pdf_path: str | Path, needle: str, *, dpi: int = 200, pad: float = 4.0
) -> tuple[bytes, dict[str, Any]] | None:
    """Locate ``needle`` text in the PDF and return (PNG bytes, bbox), or None."""
    import fitz  # PyMuPDF

    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            rects = page.search_for(needle)
            if not rects:
                continue
            rect = rects[0]
            clip = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)
            pixmap = page.get_pixmap(dpi=dpi, clip=clip)
            bbox = {
                "page": page.number,
                "x0": rect.x0,
                "y0": rect.y0,
                "x1": rect.x1,
                "y1": rect.y1,
            }
            return pixmap.tobytes("png"), bbox
    return None


def crop_region_from_pdf(session: Session, topic: Topic, region: MathRegion) -> bytes | None:
    """Default cropper: find + crop the region in the document's cached PDF."""
    chapter = session.get(Chapter, topic.chapter_id)
    document = session.get(Document, chapter.document_id) if chapter else None
    if document is None:
        return None
    pdf_path = UPLOADS_DIR / f"{document.file_hash}.pdf"
    if not pdf_path.is_file():
        return None
    found = crop_pdf_region(pdf_path, region.text)
    if found is None:
        return None
    image, region.bbox = found
    return image


def make_formula_processor(
    waterfall: Waterfall,
    *,
    source_loader: SourceLoader = load_topic_source,
    detector: Callable[[str], list[MathRegion]] = detect_math_regions,
    cropper: RegionCropper = crop_region_from_pdf,
    max_tokens: int = FORMULA_MAX_TOKENS,
) -> Callable[[QueueJob, Session], ProviderResult]:
    """Build the queue ``StageProcessor`` for the formula stage."""

    def process(job: QueueJob, session: Session) -> ProviderResult:
        topic = session.get(Topic, job.topic_id)
        regions = detector(source_loader(session, topic))
        if not regions:
            return ProviderResult(text="", provider=NO_OP_PROVIDER)  # no math, no spend

        note = get_or_create_ai_note(session, topic)
        last: ProviderResult | None = None
        for region in regions:
            image = cropper(session, topic, region)
            if image is None:
                continue  # couldn't locate this region; skip rather than guess
            result = waterfall.transcribe_image(image, max_tokens=max_tokens)
            session.add(
                Formula(
                    note_id=note.id,
                    latex=result.text.strip(),
                    state=FormulaState.reconstructed,
                    confidence=None,
                    bbox=region.bbox,
                )
            )
            last = result
        return last or ProviderResult(text="", provider=NO_OP_PROVIDER)

    return process
