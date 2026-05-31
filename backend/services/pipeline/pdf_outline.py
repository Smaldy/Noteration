"""Stage 2 fallback — recover a chapter/topic tree from the PDF itself.

``structure.detect_structure`` reads only the markitdown markdown, which for many
real PDFs (slide decks, lecture notes, exported presentations) carries **no** ATX
headings — so detection returns ``needs_manual`` and the user sees "structure not
recognized" even though the document is plainly structured. PyMuPDF exposes two
free, deterministic signals that markdown conversion throws away:

1. the embedded **table of contents / bookmarks** (``doc.get_toc()``), and
2. **font sizes** — headings are set noticeably larger than body text.

This module mines those signals (no model call — see docs/ai-pipeline.md Stage 2,
which sanctions a non-model fallback when no headings are found) and reuses the
same tree-assembly rules as the markdown path. PyMuPDF is imported lazily so the
package still loads without it, and the public entry point takes a path so the
service layer can inject a stub in tests.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from backend.services.pipeline.structure import (
    ProposedStructure,
    _build_tree,
    _clean_title,
)

# Leading "Slide 12:", "Diapositiva 3", "Folie 5", "Page 7" etc. — auto-generated
# bookmark prefixes that carry no real title once the number is removed.
_GENERIC_TOC_PREFIX = re.compile(
    r"^\s*(?:slide|diapositiva|diapo|folie|page|p|sezione|section)\b[\s.:#)\-]*\d*[\s.:#)\-]*",
    re.IGNORECASE,
)
# Whole-title bookmarks a tool inserts that mean nothing on their own.
_GENERIC_TOC_TITLES = {
    "default section",
    "sezione predefinita",
    "untitled section",
    "section sans titre",
}

# A heading must be this many times larger than body text to count, and look like
# words rather than a stray large glyph (a lone "=", a page number, a bullet).
_HEADING_SIZE_RATIO = 1.15
_MIN_HEADING_CHARS = 3
_MAX_HEADING_CHARS = 140
_MAX_HEADINGS = 300  # guard against pathological documents
_WORDLIKE = re.compile(r"[^\W\d_]", re.UNICODE)  # at least one letter


def extract_pdf_structure(pdf_path: str | Path) -> ProposedStructure | None:
    """Propose a tree from the PDF's outline, else its font sizes; else ``None``.

    Returns ``None`` when neither signal yields anything usable (so the caller
    keeps the ``needs_manual`` result). Never raises on a malformed/locked PDF —
    a failure to read just means "no fallback available".
    """
    try:
        import fitz  # PyMuPDF, lazy
    except ImportError:  # pragma: no cover - PyMuPDF is a hard dep in practice
        return None

    try:
        with fitz.open(str(pdf_path)) as doc:
            headings = _toc_headings(doc)
            method = "pdf_outline"
            if headings is None:
                headings = _font_headings(doc)
                method = "pdf_headings"
    except Exception:  # noqa: BLE001 - any reader error → no fallback, not a crash
        return None

    if not headings:
        return None
    chapters = _build_tree(headings)
    if not chapters:
        return None
    return ProposedStructure(chapters=chapters, needs_manual=False, method=method)


# --- embedded outline / bookmarks -------------------------------------------


def _toc_headings(doc) -> list[tuple[int, str]] | None:  # noqa: ANN001 - fitz.Document
    """Headings from the PDF bookmarks, or ``None`` if too few are meaningful.

    Auto-numbered "Slide N" / "Diapositiva N" bookmarks are stripped to their real
    title (and dropped when nothing remains). If most entries are generic — a deck
    exported as "Slide 1..N" with no titles — the outline is worthless and we let
    the font-size pass take over.
    """
    try:
        toc = doc.get_toc(simple=True)  # [[level, title, page], ...]
    except Exception:  # noqa: BLE001
        return None
    if not toc:
        return None

    headings: list[tuple[int, str]] = []
    for level, raw_title, *_ in toc:
        title = _meaningful_toc_title(raw_title)
        if title:
            headings.append((max(1, int(level)), title))
    headings = _collapse_consecutive(headings)

    # Require a real majority of titled entries; otherwise the bookmarks are just
    # generated slide markers and font sizes are the better signal.
    if len(headings) < 2 or len(headings) < 0.2 * len(toc):
        return None
    return headings


def _meaningful_toc_title(raw_title: str) -> str | None:
    stripped = _GENERIC_TOC_PREFIX.sub("", raw_title or "")
    title = _clean_title(stripped)
    if not title or title.lower() in _GENERIC_TOC_TITLES:
        return None
    if not _WORDLIKE.search(title):
        return None
    return title


# --- font-size heading detection --------------------------------------------


def _font_headings(doc) -> list[tuple[int, str]]:  # noqa: ANN001 - fitz.Document
    """Lines whose font is meaningfully larger than body text become headings.

    Body size is the size carrying the most characters; lines at least
    ``_HEADING_SIZE_RATIO``× larger and word-like are headings. Distinct heading
    sizes map to levels (largest → chapters, next → topics), and consecutive
    repeats — the same slide title spanning continuation slides — are collapsed.
    """
    lines = _collect_lines(doc)
    if not lines:
        return []

    char_counts: Counter[int] = Counter()
    for size, text in lines:
        char_counts[size] += len(text.replace(" ", ""))
    if not char_counts:
        return []
    body_size = char_counts.most_common(1)[0][0]
    threshold = body_size * _HEADING_SIZE_RATIO

    candidates = [
        (size, text)
        for size, text in lines
        if size >= threshold and _is_wordlike_heading(text)
    ]
    if not candidates:
        return []

    # Largest distinct heading size → level 1, next → level 2, ...
    distinct = sorted({size for size, _ in candidates}, reverse=True)
    level_of = {size: index + 1 for index, size in enumerate(distinct)}

    leveled = [(level_of[size], text) for size, text in candidates]
    return _collapse_consecutive(leveled)[:_MAX_HEADINGS]


def _collapse_consecutive(headings: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop a heading identical to the one just before it (continuation slides)."""
    collapsed: list[tuple[int, str]] = []
    for level, title in headings:
        if collapsed and collapsed[-1][1].lower() == title.lower():
            continue
        collapsed.append((level, title))
    return collapsed


def _collect_lines(doc) -> list[tuple[int, str]]:  # noqa: ANN001 - fitz.Document
    """``(rounded_size, line_text)`` for every non-empty text line, in reading order."""
    lines: list[tuple[int, str]] = []
    for page in doc:
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = _clean_title("".join(span.get("text", "") for span in spans))
                if not text:
                    continue
                size = max(
                    (round(span.get("size", 0.0)) for span in spans), default=0
                )
                lines.append((size, text))
    return lines


def _is_wordlike_heading(text: str) -> bool:
    return (
        _MIN_HEADING_CHARS <= len(text) <= _MAX_HEADING_CHARS
        and _WORDLIKE.search(text) is not None
    )
