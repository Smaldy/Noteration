"""Stage 2 fallback — recover a chapter/topic tree from the PDF itself.

``structure.detect_structure`` reads only the markitdown markdown, which for many
real PDFs (slide decks, lecture notes, exported presentations) carries **no** ATX
headings — so detection returns ``needs_manual`` and the user sees "structure not
recognized" even though the document is plainly structured. PyMuPDF exposes two
free, deterministic signals that markdown conversion throws away:

1. the embedded **table of contents / bookmarks** (``doc.get_toc()``), and
2. **font sizes** — headings are set noticeably larger than body text.

This module mines those signals (no model call — see docs/architecture.md Stage 2,
which sanctions a non-model fallback when no headings are found) and reuses the
same tree-assembly rules as the markdown path. PyMuPDF is imported lazily so the
package still loads without it, and the public entry point takes a path so the
service layer can inject a stub in tests.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from backend.services.pipeline.ingestion import OutlineEntry
from backend.services.pipeline.structure import (
    _CHAPTER_RE,
    ProposedChapter,
    ProposedStructure,
    ProposedTopic,
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

# Tool-default document titles that say nothing about the content — never use one
# to name the slide-deck chapter (substring match, lowercased).
_GENERIC_DOC_TITLE_MARKERS = (
    "powerpoint presentation",
    "presentazione standard",
    "microsoft powerpoint",
    "présentation",
    "presentación",
    "untitled",
    "presentation1",
    "document1",
    "slide1",
)
_DEFAULT_DECK_CHAPTER = "Slides"

# Consecutive slides that continue the same subject are merged into one topic, so
# a deck doesn't fragment into a topic per slide. Similarity is title word overlap
# (overlap coefficient over significant words); the run is capped so a recurring
# word can't fuse a whole section into one blob.
_MERGE_OVERLAP = 0.5
_MERGE_MAX_RUN = 3
_TOKEN_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
# Words that carry no subject signal: structural/filler terms and slide labels.
_TOPIC_STOPWORDS = frozenset(
    {
        "the", "and", "for", "our", "due", "its", "this", "that", "these", "those",
        "with", "from", "via", "per", "are", "was", "were", "has", "have", "not",
        "example", "examples", "introduction", "intro", "overview", "summary",
        "conclusion", "conclusions", "part", "slide", "slides", "chapter", "section",
        "demo", "about", "using", "use", "general", "basic", "basics",
        # filler / quantifiers that carry no subject signal
        "some", "many", "more", "most", "few", "all", "new", "key", "main",
        "various", "several", "into", "what", "how", "why", "when", "which",
        "between", "their", "there", "here", "such", "than", "then", "also",
        "del", "della", "delle", "dei", "degli", "come", "che", "con",
    }
)


# Front/back matter that is never worth generating notes or assessment for. A
# deterministic string match (no AI) — case-insensitive against the stripped TOC
# title — flags these to auto-skip so the user isn't deselecting them every upload.
TRASH_TITLES: frozenset[str] = frozenset(
    {
        "cover",
        "copyright",
        "dedication",
        "preface",
        "acknowledgments",
        "acknowledgements",
        "brief contents",
        "table of contents",
        "contents",
        "references",
        "bibliography",
        "index",
        "about the authors",
        "about the author",
        "digital resources for students",
        "digital resources",
        "title page",
        "foreword",
        "colophon",
    }
)


@dataclass
class ChapterSlice:
    """One top-level chapter recovered from a PDF's outline, with its page span."""

    title: str
    page_start: int  # 1-indexed, inclusive
    page_end: int  # 1-indexed, inclusive
    auto_skip: bool  # True for trash front/back matter or single-page entries


def is_trash(title: str) -> bool:
    """True when a chapter title is front/back matter we always auto-skip."""
    return title.strip().lower() in TRASH_TITLES


def extract_chapters_from_toc(
    outline: list[OutlineEntry],
    total_pages: int,
) -> list[ChapterSlice]:
    """Slice a PDF's top-level (level 1) TOC entries into chapters with page spans.

    A chapter runs from its own start page to one page before the next chapter's
    start; the last chapter runs to ``total_pages``. Trash titles and single-page
    entries (front matter) are returned too, marked ``auto_skip`` so the user can
    still un-skip them in review.
    """
    level1 = [
        (title.strip(), page) for level, title, page in outline if level == 1
    ]
    slices: list[ChapterSlice] = []
    for index, (title, page_start) in enumerate(level1):
        if index + 1 < len(level1):
            page_end = level1[index + 1][1] - 1
        else:
            page_end = total_pages
        # Guard against a non-monotonic outline: never end before we start.
        page_end = max(page_end, page_start)
        auto_skip = is_trash(title) or page_start == page_end
        slices.append(ChapterSlice(title, page_start, page_end, auto_skip))
    return slices


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
            if not headings:
                return None
            chapters = _assemble(headings, _deck_title(doc))
    except Exception:  # noqa: BLE001 - any reader error → no fallback, not a crash
        return None

    if not chapters:
        return None
    return ProposedStructure(chapters=chapters, needs_manual=False, method=method)


def _assemble(
    headings: list[tuple[int, str]], deck_title: str | None
) -> list[ProposedChapter]:
    """Map recovered headings to a tree, grouping slide decks into one unit.

    A book (or a deck with named sections) carries hierarchy — more than one
    heading level — so the topmost level becomes chapters and deeper levels become
    topics (the same rule as the markdown path). A presentation is instead a flat
    list of slide titles; turning each slide into its own chapter buries the
    document in 20–40 one-topic chapters, so a flat run collapses into a **single**
    chapter (named from the file when it carries a real title) with every slide as
    a topic. A flat list that still looks like real chapter headings ("Chapter N",
    "Part N") is kept as chapters — that's a book with a flat outline, not slides.
    """
    levels = {level for level, _ in headings}
    titles = [title for _, title in headings]
    if len(levels) > 1 or _looks_chaptered(titles):
        return _build_tree(headings)
    merged = _merge_consecutive_related(titles)
    return [
        ProposedChapter(
            title=deck_title or _DEFAULT_DECK_CHAPTER,
            order_index=0,
            topics=[ProposedTopic(title=t, order_index=i) for i, t in enumerate(merged)],
        )
    ]


def _merge_consecutive_related(titles: list[str]) -> list[str]:
    """Fold runs of consecutive slides on the same subject into one topic title.

    Two adjacent slides belong together when their titles share enough significant
    words (overlap coefficient ≥ ``_MERGE_OVERLAP``) — e.g. "Forces and Kinetic
    energy of rolling" + "Forces of rolling". Each new slide is compared to the
    *first* slide of the current run (not the previous one) so a single shared word
    can't let the run drift across unrelated subjects, and a run spans at most
    ``_MERGE_MAX_RUN`` slides. The kept title is the run's first slide; the user
    refines in review.
    """
    merged: list[str] = []
    anchor_words: set[str] = set()
    run_length = 0
    for title in titles:
        words = _content_words(title)
        if merged and run_length < _MERGE_MAX_RUN and _related(anchor_words, words):
            run_length += 1
            continue
        merged.append(title)
        anchor_words = words
        run_length = 1
    return merged


def _content_words(title: str) -> set[str]:
    return {
        word
        for match in _TOKEN_RE.finditer(title.lower())
        if len(word := match.group()) >= 3 and word not in _TOPIC_STOPWORDS
    }


def _related(anchor_words: set[str], words: set[str]) -> bool:
    if not anchor_words or not words:
        return False
    overlap = len(anchor_words & words)
    return overlap > 0 and overlap / min(len(anchor_words), len(words)) >= _MERGE_OVERLAP


def _looks_chaptered(titles: list[str]) -> bool:
    """True when a clear majority of a flat list are "Chapter/Part/Unit N" lines."""
    if len(titles) < 2:
        return False
    hits = sum(1 for title in titles if _CHAPTER_RE.match(title))
    return hits >= max(2, 0.6 * len(titles))


def _deck_title(doc) -> str | None:  # noqa: ANN001 - fitz.Document
    """A meaningful document title from PDF metadata, else ``None``.

    Authoring tools stamp generic titles ("PowerPoint Presentation",
    "Presentazione standard di PowerPoint") that name nothing — those are rejected
    so the deck chapter falls back to a neutral label the user renames in review.
    """
    metadata = doc.metadata or {}
    title = _clean_title(metadata.get("title") or "")
    if not title or not _WORDLIKE.search(title):
        return None
    lowered = title.lower()
    if any(marker in lowered for marker in _GENERIC_DOC_TITLE_MARKERS):
        return None
    return title


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
