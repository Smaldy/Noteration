"""Stage 1 — Exercise extraction (synchronous vision call, per page).

Reads each cached page render of the uploaded exercise PDF through the vision
``Waterfall`` (the same path as formula transcription, with a custom extraction
prompt) and parses a JSON array of exercises per page. Parsing is tolerant —
malformed items are skipped with a warning — and exercises are de-duplicated
across pages so a problem continued onto the next page isn't counted twice.

Like the other pipeline stages this module is DB-light: it builds prompts, calls
the model, parses, and attaches ``ExtractedExercise`` rows to the given
``ExerciseSession`` *uncommitted* (the session service owns the transaction). The
page-image loader is injected so the orchestration is unit-testable without a
real ingestion cache.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.models.duplicator import ExerciseSession, ExtractedExercise
from backend.models.enums import ExerciseSessionStatus
from backend.services.pipeline.ingestion import CACHE_ROOT, PAGES_DIRNAME
from backend.services.providers.waterfall import Waterfall

logger = logging.getLogger(__name__)

# One page of exercises is a short JSON array; keep the vision spend bounded.
EXTRACTION_MAX_TOKENS = 4096
# Two normalised exercise texts at/above this similarity are treated as the same
# problem (a continuation across a page break), so the later one is dropped.
DEDUP_THRESHOLD = 0.90

# Loader: a PDF content hash → its page-image PNG bytes, in page order.
PageLoader = Callable[[str], "list[bytes]"]


@dataclass
class ParsedExercise:
    """One exercise lifted from a page response, before persistence."""

    raw_text: str
    topic: str
    subtopic: str | None = None
    difficulty_signals: list[str] = field(default_factory=list)
    viz: dict[str, Any] | None = None


def build_extraction_prompt(year_level: int, subject_hint: str | None) -> str:
    """Vision prompt: pull every exercise on a page out as a JSON array.

    States that the problems are from a university mathematics/physics major at the
    given year level, asks for dot-notation topic classification, and requests a
    ``viz`` block only when a visual would directly aid solving the problem.
    """
    hint_line = (
        f"- Subject context (use it to classify topics): {subject_hint.strip()}\n"
        if subject_hint and subject_hint.strip()
        else ""
    )
    return (
        "You are reading ONE page of a university-level mathematics or physics "
        "problem set or exam. The problems are written for a university "
        f"mathematics/physics major, year level {year_level} (1 = first year … "
        "5 = final year).\n\n"
        "Extract every distinct exercise/problem visible on this page. Respond with "
        "ONLY a JSON array — no prose, no markdown, no code fences. Each element:\n"
        "{\n"
        '  "order_index": int,            // 0-based position on this page\n'
        '  "raw_text": str,               // the full problem statement, verbatim\n'
        '  "topic": str,                  // dot notation, e.g. '
        '"complex_analysis.residues", "classical_mechanics.projectile", '
        '"abstract_algebra.subgroups"\n'
        '  "subtopic": str | null,\n'
        '  "difficulty_signals": [str],   // short keywords, e.g. ["proof", '
        '"multi_step"]\n'
        '  "viz": null | {"type": "...", "expression": "...", "domain": [a, b], '
        '"pieces": [{"expression": "...", "domain": [a, b]}], "params": {}}\n'
        "}\n\n"
        "Rules:\n"
        f"{hint_line}"
        "- Classify `topic` with dot notation (branch.area). Be specific.\n"
        "- Include a `viz` block ONLY when a visual would directly aid solving the "
        "problem — never decoratively. Otherwise `viz` is null. Valid `viz.type` "
        "values: mafs_function (single-variable y=f(x)), mafs_parametric (2D "
        "parametric curve), plotly_3d (surface f(x,y) / 3D), plotly_complex "
        "(complex-valued function on the Argand plane), matter_simulation "
        "(dynamics over time: projectile/pendulum/collision/spring), force_diagram "
        "(static force/torque arrows).\n"
        "- Use mathjs syntax for every expression: `exp(-x)`, `x^2`, `sin(x)`, "
        "`log(x)` (variable `x`; `t` for parametric).\n"
        "- For a PIECEWISE function or a system defined by cases (e.g. f(x) = "
        "e^-x for x<2, (x-2)e^-x for x>=2), use type mafs_function with `pieces`: "
        "an ordered list of {expression, domain:[a,b]} branches — one per case, "
        "each domain being the x-interval where that branch applies — instead of a "
        "single `expression`. Omit `pieces` for ordinary single-formula graphs.\n"
        "- A proof, algebra, or combinatorics problem usually has no useful "
        "visualization → `viz` is null.\n"
        "- If the page contains no exercises, return [].\n"
    )


def load_page_images(pdf_hash: str, *, cache_root: str | Path = CACHE_ROOT) -> list[bytes]:
    """Read the cached page renders for ``pdf_hash`` as PNG bytes, in page order.

    Pages are written by ingestion under ``cache/<hash>/pages/page-NNNN.png``.
    Returns an empty list when the cache directory is absent.
    """
    pages_dir = Path(cache_root) / pdf_hash / PAGES_DIRNAME
    if not pages_dir.is_dir():
        return []
    return [p.read_bytes() for p in sorted(pages_dir.glob("*.png"))]


def _extract_json_array(text: str) -> str:
    """Pull the JSON array out of a model response (tolerates fences/prose)."""
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON array found in response")
    return text[start : end + 1]


def parse_exercises(text: str) -> list[ParsedExercise]:
    """Parse one page's response into exercises, skipping malformed items.

    Tolerant by design (vision output is noisy): a response with no usable array,
    or individual items that aren't well-formed, yield as many valid exercises as
    can be recovered rather than raising.
    """
    try:
        data = json.loads(_extract_json_array(text))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("duplicator: unparseable extraction response: %s", exc)
        return []
    if not isinstance(data, list):
        return []

    exercises: list[ParsedExercise] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw_text = item.get("raw_text")
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue
        topic = item.get("topic")
        topic = topic.strip() if isinstance(topic, str) and topic.strip() else "general"
        subtopic = item.get("subtopic")
        subtopic = subtopic.strip() if isinstance(subtopic, str) and subtopic.strip() else None
        signals = item.get("difficulty_signals")
        signals = (
            [s.strip() for s in signals if isinstance(s, str) and s.strip()]
            if isinstance(signals, list)
            else []
        )
        viz = item.get("viz")
        viz = viz if isinstance(viz, dict) else None
        exercises.append(
            ParsedExercise(
                raw_text=raw_text.strip(),
                topic=topic,
                subtopic=subtopic,
                difficulty_signals=signals,
                viz=viz,
            )
        )
    return exercises


def _normalize(text: str) -> str:
    """Lowercase + collapse whitespace, for similarity comparison."""
    return " ".join(text.lower().split())


def _is_duplicate(normalized: str, seen: list[str]) -> bool:
    """True when ``normalized`` is > ``DEDUP_THRESHOLD`` similar to a seen text."""
    return any(
        SequenceMatcher(None, normalized, other).ratio() >= DEDUP_THRESHOLD
        for other in seen
    )


def extract_exercises(
    session: Session,
    exercise_session: ExerciseSession,
    waterfall: Waterfall,
    *,
    load_pages: PageLoader = load_page_images,
) -> list[ExtractedExercise]:
    """Extract every exercise from the session's PDF and attach the rows.

    Calls the vision waterfall once per cached page with the extraction prompt,
    parses each page tolerantly, de-duplicates across pages (a problem continued
    onto the next page is dropped), persists ``ExtractedExercise`` rows on
    ``exercise_session`` (uncommitted — the caller owns the transaction), flips the
    session to ``ready``, and returns the rows in reading order.

    Provider-exhaustion errors propagate so the caller/router can surface them; the
    session is left in ``extracting`` (the caller rolls back).
    """
    prompt = build_extraction_prompt(
        exercise_session.year_level, exercise_session.subject_hint
    )
    pages = load_pages(exercise_session.document_hash)

    seen_norms: list[str] = []
    rows: list[ExtractedExercise] = []
    for page_bytes in pages:
        result = waterfall.transcribe_image(
            page_bytes, max_tokens=EXTRACTION_MAX_TOKENS, prompt=prompt
        )
        for parsed in parse_exercises(result.text):
            normalized = _normalize(parsed.raw_text)
            if not normalized or _is_duplicate(normalized, seen_norms):
                continue
            seen_norms.append(normalized)
            row = ExtractedExercise(
                session=exercise_session,
                order_index=len(rows),
                raw_text=parsed.raw_text,
                topic=parsed.topic,
                subtopic=parsed.subtopic,
                difficulty_signals=parsed.difficulty_signals,
                viz=parsed.viz,
            )
            session.add(row)
            rows.append(row)

    exercise_session.status = ExerciseSessionStatus.ready
    session.flush()  # assign ids (the search-job enqueue in ED-3 needs them)
    return rows
