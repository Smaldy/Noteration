"""Stage 2b — optional AI grouping of slide titles into a coherent topic tree.

The heuristic deck path (``pdf_outline._merge_consecutive_related``) can only
merge *adjacent* slides whose titles share words, so a professor's deck that
spends five differently-titled slides on one subject — or revisits a subject
later — still fragments into near-duplicate topics (user-reported: "5 topics
about the same thing"). Every fragment is a separate generation call, so the
fragmentation wastes quota as well as producing repetitive notes.

This module fixes that with ONE tiny model call over the slide *titles only*
(a 40-slide deck is a few hundred input tokens — noise next to the per-topic
generation calls it saves): the model groups the slides into study topics and
chapters and flags no-content slides (agenda, logistics, "questions?") to drop.
Slide page lists ride along so each grouped topic knows exactly which PDF pages
its content lives on — generation then slices those pages instead of guessing
proportionally.

The call is optional and fallible by design: the caller (documents service)
falls back to the heuristic tree when no provider has headroom or the output is
unusable, and caches a successful grouping on disk so re-opening the review
screen never re-pays the call.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.services.pipeline.generation import (
    GenerationParseError,
    _load_object,
)
from backend.services.pipeline.ingestion import atomic_write_text
from backend.services.pipeline.structure import (
    ProposedChapter,
    ProposedTopic,
    SlideRun,
)
from backend.services.providers.waterfall import Waterfall

# Output cap — the response is titles + slide numbers, small even for a large
# deck (the heading scan is already capped at 300 slides upstream).
SLIDE_GROUPING_MAX_TOKENS = 4096

# Decks smaller than this don't fragment enough to be worth a model call — the
# heuristic merge handles them fine.
MIN_SLIDES_FOR_GROUPING = 6

SLIDE_GROUPING_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "chapters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "topics": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "slides": {
                                    "type": "array",
                                    "items": {"type": "integer"},
                                },
                            },
                            "required": ["title", "slides"],
                        },
                    },
                },
                "required": ["title", "topics"],
            },
        },
        "skip": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["chapters"],
}


def build_slide_grouping_prompt(titles: list[str]) -> str:
    """Prompt asking the model to organize numbered slide titles into a tree."""
    numbered = "\n".join(f"{i}. {title}" for i, title in enumerate(titles, start=1))
    return (
        "You are organizing a university lecture slide deck into study units. "
        "Below are the deck's slide titles, in order.\n\n"
        "Group the slides into TOPICS: one topic = one coherent, studyable "
        "subject. Merge consecutive slides on the same subject AND slides that "
        "revisit the same subject later in the deck. Group related topics into "
        "CHAPTERS (a deck usually has 1-4).\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        "fences):\n"
        '{"chapters": [{"title": str, "topics": [{"title": str, '
        '"slides": [int, ...]}]}], "skip": [int, ...]}\n'
        "- topics.slides: the slide numbers belonging to that topic. Every slide "
        "number from 1 to N must appear exactly once — in one topic, or in "
        '"skip".\n'
        '- skip: slides with no study content (title/agenda slides, course '
        'logistics, "any questions?", bibliography, recap of a previous '
        "lecture, empty section dividers).\n"
        "- title: a concise name for the subject, in the same language as the "
        "slide titles — not just a copy of one slide's title.\n"
        "- Keep chapters and topics in the order their content appears in the "
        "deck.\n\n"
        f"# Slides\n{numbered}\n"
    )


@dataclass
class _Group:
    """One parsed topic: its chapter index, title, and 1-indexed slide numbers."""

    chapter: int
    title: str
    slides: list[int]


def parse_slide_grouping(
    text: str, slide_count: int
) -> tuple[list[str], list[_Group]]:
    """Parse + repair the grouping JSON → (chapter titles, topic groups).

    Repair rules (the model output must never silently lose deck content):
    - out-of-range / non-integer slide numbers are dropped;
    - a slide assigned twice keeps its first assignment;
    - a slide in ``skip`` is excluded from topics (skip wins only if unassigned);
    - a slide mentioned nowhere is attached to the topic holding the nearest
      preceding slide (nearest following when there is none before it).

    Raises ``GenerationParseError`` when nothing usable remains.
    """
    data = _load_object(text)
    if not isinstance(data.get("chapters"), list):
        raise GenerationParseError("grouping is not an object with chapters")

    chapter_titles: list[str] = []
    groups: list[_Group] = []
    assigned: set[int] = set()
    for chapter in data["chapters"]:
        if not isinstance(chapter, dict):
            continue
        title = str(chapter.get("title") or "").strip()
        topics = chapter.get("topics")
        if not title or not isinstance(topics, list):
            continue
        chapter_index = len(chapter_titles)
        chapter_titles.append(title)
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            topic_title = str(topic.get("title") or "").strip()
            slide_nums = topic.get("slides")
            if not topic_title or not isinstance(slide_nums, list):
                continue
            slides = [
                n
                for n in slide_nums
                if isinstance(n, int)
                and not isinstance(n, bool)
                and 1 <= n <= slide_count
                and n not in assigned
            ]
            if not slides:
                continue
            assigned.update(slides)
            groups.append(_Group(chapter_index, topic_title, sorted(slides)))
    if not groups:
        raise GenerationParseError("grouping contains no usable topics")

    skipped = {
        n
        for n in (data.get("skip") or [])
        if isinstance(n, int) and not isinstance(n, bool) and n not in assigned
    }
    # A model that skips most of the deck is misreading the task, not curating it.
    if len(skipped) > slide_count // 2:
        raise GenerationParseError("grouping skipped most of the deck")

    _attach_unassigned(groups, assigned | skipped, slide_count)
    return chapter_titles, groups


def _attach_unassigned(
    groups: list[_Group], accounted: set[int], slide_count: int
) -> None:
    """Give every unmentioned slide to the topic of its nearest assigned slide."""
    slide_group: dict[int, _Group] = {}
    for group in groups:
        for n in group.slides:
            slide_group[n] = group
    for n in range(1, slide_count + 1):
        if n in accounted:
            continue
        home = None
        for prev in range(n - 1, 0, -1):
            if prev in slide_group:
                home = slide_group[prev]
                break
        if home is None:
            for nxt in range(n + 1, slide_count + 1):
                if nxt in slide_group:
                    home = slide_group[nxt]
                    break
        if home is not None:  # pragma: no branch - groups is never empty here
            home.slides.append(n)
            home.slides.sort()
            slide_group[n] = home


def group_slides(waterfall: Waterfall, slides: list[SlideRun]) -> list[ProposedChapter]:
    """ONE model call: group a deck's slides into a proposed chapter/topic tree.

    ``slides`` is the detection pass's ``(title, pages)`` list (pages already
    gap-filled, so unioning slide page lists never loses content). Raises
    ``GenerationParseError`` on unusable output and lets provider exhaustion
    propagate — the caller decides whether to fall back to the heuristic tree.
    """
    prompt = build_slide_grouping_prompt([title for title, _ in slides])
    result = waterfall.generate(
        prompt,
        max_tokens=SLIDE_GROUPING_MAX_TOKENS,
        response_schema=SLIDE_GROUPING_SCHEMA,
    )
    chapter_titles, groups = parse_slide_grouping(result.text, len(slides))
    return build_grouped_chapters(chapter_titles, groups, slides)


def build_grouped_chapters(
    chapter_titles: list[str],
    groups: list[_Group],
    slides: list[SlideRun],
) -> list[ProposedChapter]:
    """Materialize parsed groups into proposed chapters with per-topic pages.

    Topics keep deck reading order (by their first slide) inside each chapter,
    and chapters are ordered by their first topic's first slide; a chapter's page
    range spans its topics' pages (min→max) for the review UI.
    """
    by_chapter: dict[int, list[_Group]] = {}
    for group in groups:
        by_chapter.setdefault(group.chapter, []).append(group)

    ordered_chapters = sorted(
        by_chapter.items(), key=lambda kv: min(min(g.slides) for g in kv[1])
    )
    chapters: list[ProposedChapter] = []
    for chapter_index, chapter_groups in ordered_chapters:
        topics = []
        for group in sorted(chapter_groups, key=lambda g: min(g.slides)):
            pages = sorted(
                {page for n in group.slides for page in slides[n - 1][1]}
            )
            topics.append(
                ProposedTopic(
                    title=group.title, order_index=len(topics), pages=pages
                )
            )
        all_pages = [page for topic in topics for page in topic.pages]
        chapters.append(
            ProposedChapter(
                title=chapter_titles[chapter_index],
                order_index=len(chapters),
                topics=topics,
                page_start=min(all_pages),
                page_end=max(all_pages),
            )
        )
    return chapters


# --- disk cache (per file hash, same layout as the ingestion caches) ---------

# cache/<hash>/slide_grouping.json — a successful grouping is never re-paid.
SLIDE_GROUPING_CACHE = "slide_grouping.json"


def load_cached_grouping(
    cache_root: str | Path, file_hash: str
) -> list[ProposedChapter] | None:
    """A previously cached grouping for this document, or ``None``.

    Self-contained (no PDF or slide list needed), so detection can serve a
    grouped deck without re-running the whole-document heading scan.
    """
    if not file_hash:
        return None
    path = Path(cache_root) / file_hash / SLIDE_GROUPING_CACHE
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return chapters_from_payload(payload)


def store_cached_grouping(
    cache_root: str | Path, file_hash: str, chapters: list[ProposedChapter]
) -> None:
    """Persist a successful grouping (atomic, like every cache artifact)."""
    if not file_hash:
        return
    atomic_write_text(
        Path(cache_root) / file_hash / SLIDE_GROUPING_CACHE,
        json.dumps(chapters_to_payload(chapters)),
    )


def chapters_to_payload(chapters: list[ProposedChapter]) -> dict:
    """A grouped tree as a JSON-safe dict for the per-hash detection cache."""
    return {
        "version": 1,
        "chapters": [
            {
                "title": chapter.title,
                "page_start": chapter.page_start,
                "page_end": chapter.page_end,
                "topics": [
                    {"title": topic.title, "pages": topic.pages}
                    for topic in chapter.topics
                ],
            }
            for chapter in chapters
        ],
    }


def chapters_from_payload(payload: dict) -> list[ProposedChapter] | None:
    """Rebuild a cached grouped tree; ``None`` when the payload is unusable."""
    if not isinstance(payload, dict) or payload.get("version") != 1:
        return None
    chapters: list[ProposedChapter] = []
    try:
        for index, chapter in enumerate(payload["chapters"]):
            topics = [
                ProposedTopic(
                    title=topic["title"],
                    order_index=t_index,
                    pages=[int(p) for p in topic["pages"]],
                )
                for t_index, topic in enumerate(chapter["topics"])
            ]
            if not topics:
                return None
            chapters.append(
                ProposedChapter(
                    title=chapter["title"],
                    order_index=index,
                    topics=topics,
                    page_start=chapter.get("page_start"),
                    page_end=chapter.get("page_end"),
                )
            )
    except (KeyError, TypeError, ValueError):
        return None
    return chapters or None
