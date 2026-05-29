"""Stage 2 — Structure detection: ingested markdown → proposed chapter/topic tree.

Heuristic only, no model call (docs/ai-pipeline.md stage 2): scan the markitdown
output for heading structure and propose a two-level tree the user then reviews
(rename / merge / split / set priority) before confirming. When no usable headings
exist (e.g. a scanned PDF), ``needs_manual`` is set so the UI offers the manual
definition fallback instead of proposing a misleading empty/garbled tree.

Detection rules (locked here; see DECISIONS in docs/build-log.md):
- Primary signal is Markdown ATX headings (``#``..``######``), which markitdown
  emits for PDFs that retain a text structure. Fenced code blocks are ignored.
- Fallback when there are no ATX headings: lines like "Chapter/Unit/Part N[: ..]"
  (N decimal or Roman) become chapters. This is deliberately conservative —
  decimal list numbering in prose is too false-positive-prone to treat as
  structure, so anything finer falls through to the manual path.
- Mapping: the *topmost* heading level present becomes chapters; any deeper level
  becomes topics under the current chapter. Every chapter is guaranteed at least
  one topic (defaulting to the chapter title) so it is always a processable unit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# ATX heading: up to 3 leading spaces, 1-6 '#', a space, the title, optional
# trailing '#'s. (Setext '===' underlines are rare in markitdown output.)
_ATX_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*#*[ \t]*$")

# Textual fallback: "Chapter|Unit|Part <num>[: title]" (num decimal or Roman).
_CHAPTER_RE = re.compile(
    r"^\s*(?:chapter|unit|part)\s+(?:\d+|[ivxlcdm]+)\b[\s:.)\-]*",
    re.IGNORECASE,
)

_FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass
class ProposedTopic:
    title: str
    order_index: int


@dataclass
class ProposedChapter:
    title: str
    order_index: int
    topics: list[ProposedTopic] = field(default_factory=list)


@dataclass
class ProposedStructure:
    chapters: list[ProposedChapter]
    needs_manual: bool  # no usable headings → user defines the tree manually
    method: str  # 'markdown' | 'text' | 'manual'


def detect_structure(markdown: str) -> ProposedStructure:
    """Propose a chapter/topic tree from ingested markdown (pure, no model)."""
    headings = _extract_atx_headings(markdown)
    method = "markdown"
    if not headings:
        headings = _extract_text_chapters(markdown)
        method = "text"
    if not headings:
        return ProposedStructure(chapters=[], needs_manual=True, method="manual")

    chapters = _build_tree(headings)
    if not chapters:
        return ProposedStructure(chapters=[], needs_manual=True, method="manual")
    return ProposedStructure(chapters=chapters, needs_manual=False, method=method)


# --- heading extraction -----------------------------------------------------


def iter_atx_headings(markdown: str) -> list[tuple[int, str, int]]:
    """Return ``(level, title, line_no)`` for each ATX heading outside fences.

    ``line_no`` indexes ``markdown.splitlines()`` so callers can slice the source
    section that follows a heading (used by generation's per-topic source loader).
    """
    headings: list[tuple[int, str, int]] = []
    in_fence = False
    for line_no, line in enumerate(markdown.splitlines()):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _ATX_RE.match(line)
        if not match:
            continue
        title = _clean_title(match.group(2))
        if title:
            headings.append((len(match.group(1)), title, line_no))
    return headings


def _extract_atx_headings(markdown: str) -> list[tuple[int, str]]:
    """Return ``(level, title)`` for each ATX heading outside code fences."""
    return [(level, title) for level, title, _ in iter_atx_headings(markdown)]


def _extract_text_chapters(markdown: str) -> list[tuple[int, str]]:
    """Fallback: 'Chapter/Unit/Part N' lines as level-1 headings (no fences)."""
    headings: list[tuple[int, str]] = []
    in_fence = False
    for line in markdown.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _CHAPTER_RE.match(line):
            title = _clean_title(line)
            if title:
                headings.append((1, title))
    return headings


# --- tree assembly ----------------------------------------------------------


def _build_tree(headings: list[tuple[int, str]]) -> list[ProposedChapter]:
    """Topmost level → chapters; deeper → topics; every chapter gets ≥1 topic."""
    chapter_level = min(level for level, _ in headings)
    chapters: list[ProposedChapter] = []
    current: ProposedChapter | None = None

    def open_chapter(title: str) -> ProposedChapter:
        chapter = ProposedChapter(title=title, order_index=len(chapters))
        chapters.append(chapter)
        return chapter

    for level, title in headings:
        if level == chapter_level:
            current = open_chapter(title)
            continue
        if current is None:
            # A deeper heading before any chapter-level one gets a synthetic
            # chapter so its content is never dropped.
            current = open_chapter("Chapter 1")
        current.topics.append(ProposedTopic(title=title, order_index=len(current.topics)))

    # A chapter heading with no sub-headings still needs a processable unit.
    for chapter in chapters:
        if not chapter.topics:
            chapter.topics.append(ProposedTopic(title=chapter.title, order_index=0))
    return chapters


def _clean_title(text: str) -> str:
    """Collapse whitespace and strip markdown emphasis/heading punctuation."""
    return re.sub(r"\s+", " ", text).strip(" \t#*_`").strip()
