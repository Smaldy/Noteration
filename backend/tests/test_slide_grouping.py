"""AI slide grouping (Stage 2b) + per-topic page slicing.

Covers: grouping-response parsing/repair (no slide is ever silently lost), the
grouped tree's page unions, detection wiring (grouper injected; disk cache;
heuristic fallback on failure), page persistence through confirm, and the
``get_pages_markdown`` source primitive that gives a page-mapped topic exactly
its slides' text.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.schemas.structure import ChapterIn, TopicIn
from backend.services import documents as docsvc
from backend.services.pipeline import generation
from backend.services.pipeline.generation import GenerationParseError
from backend.services.pipeline.ingestion import get_pages_markdown
from backend.services.pipeline.slide_grouping import (
    build_grouped_chapters,
    chapters_from_payload,
    chapters_to_payload,
    group_slides,
    parse_slide_grouping,
)
from backend.services.pipeline.structure import (
    ProposedChapter,
    ProposedStructure,
    ProposedTopic,
)
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall

# A 7-slide deck: gap-filled (title, pages) pairs as the detection pass emits.
SLIDES: list[tuple[str, list[int]]] = [
    ("Intro to rolling", [1]),
    ("Forces of rolling", [2, 3]),  # continuation slide folded in
    ("Energy of rolling", [4]),
    ("Angular momentum", [5]),
    ("Torque", [6]),
    ("Questions?", [7]),
]

_GROUPING = json.dumps(
    {
        "chapters": [
            {
                "title": "Rolling motion",
                "topics": [
                    {"title": "Rolling dynamics", "slides": [1, 2]},
                    {"title": "Energy of rolling", "slides": [3]},
                ],
            },
            {
                "title": "Rotation",
                "topics": [{"title": "Angular momentum and torque", "slides": [4, 5]}],
            },
        ],
        "skip": [6],
    }
)


# --- parsing + repair ---------------------------------------------------------


def test_parse_valid_grouping() -> None:
    chapter_titles, groups = parse_slide_grouping(_GROUPING, slide_count=6)
    assert chapter_titles == ["Rolling motion", "Rotation"]
    assert [(g.chapter, g.title, g.slides) for g in groups] == [
        (0, "Rolling dynamics", [1, 2]),
        (0, "Energy of rolling", [3]),
        (1, "Angular momentum and torque", [4, 5]),
    ]


def test_parse_repairs_duplicates_and_out_of_range() -> None:
    text = json.dumps(
        {
            "chapters": [
                {
                    "title": "C",
                    "topics": [
                        {"title": "A", "slides": [1, 2, 99]},  # 99 out of range
                        {"title": "B", "slides": [2, 3]},  # 2 already taken
                    ],
                }
            ]
        }
    )
    _, groups = parse_slide_grouping(text, slide_count=3)
    assert [g.slides for g in groups] == [[1, 2], [3]]


def test_parse_attaches_unmentioned_slides_to_nearest_topic() -> None:
    text = json.dumps(
        {
            "chapters": [
                {
                    "title": "C",
                    "topics": [
                        {"title": "A", "slides": [1]},
                        {"title": "B", "slides": [4]},
                    ],
                }
            ]
        }
    )
    _, groups = parse_slide_grouping(text, slide_count=5)
    # 2 and 3 follow slide 1 → topic A; 5 follows 4 → topic B. Nothing lost.
    assert [g.slides for g in groups] == [[1, 2, 3], [4, 5]]


def test_parse_rejects_grouping_that_skips_most_of_the_deck() -> None:
    text = json.dumps(
        {
            "chapters": [{"title": "C", "topics": [{"title": "A", "slides": [1]}]}],
            "skip": [2, 3, 4, 5, 6],
        }
    )
    with pytest.raises(GenerationParseError):
        parse_slide_grouping(text, slide_count=6)


def test_parse_rejects_empty_grouping() -> None:
    with pytest.raises(GenerationParseError):
        parse_slide_grouping(json.dumps({"chapters": []}), slide_count=3)


# --- grouped tree building ----------------------------------------------------


def test_grouped_chapters_union_pages_and_span_ranges() -> None:
    chapter_titles, groups = parse_slide_grouping(_GROUPING, slide_count=6)
    chapters = build_grouped_chapters(chapter_titles, groups, SLIDES)

    assert [c.title for c in chapters] == ["Rolling motion", "Rotation"]
    rolling = chapters[0]
    # "Rolling dynamics" = slides 1+2, and slide 2 spans pages 2-3 → [1, 2, 3].
    assert [t.pages for t in rolling.topics] == [[1, 2, 3], [4]]
    assert (rolling.page_start, rolling.page_end) == (1, 4)
    rotation = chapters[1]
    assert [t.pages for t in rotation.topics] == [[5, 6]]
    # Skipped slide 6 ("Questions?") is in no topic... its page belongs to slide
    # 5's gap-filled list? No: slide 5 ("Torque") covers page 6 in SLIDES, and
    # slide 6 covers page 7, which was skipped → page 7 appears nowhere.
    all_pages = {p for c in chapters for t in c.topics for p in t.pages}
    assert 7 not in all_pages


def test_group_slides_one_call_through_waterfall() -> None:
    provider = MockProvider("gemini", text=_GROUPING)
    chapters = group_slides(Waterfall(providers=[provider]), SLIDES)
    assert [c.title for c in chapters] == ["Rolling motion", "Rotation"]
    assert provider.generate_calls == 1


def test_payload_round_trip() -> None:
    chapter_titles, groups = parse_slide_grouping(_GROUPING, slide_count=6)
    chapters = build_grouped_chapters(chapter_titles, groups, SLIDES)
    rebuilt = chapters_from_payload(chapters_to_payload(chapters))
    assert rebuilt is not None
    assert [c.title for c in rebuilt] == [c.title for c in chapters]
    assert [t.pages for c in rebuilt for t in c.topics] == [
        t.pages for c in chapters for t in c.topics
    ]


def test_payload_rejects_garbage() -> None:
    assert chapters_from_payload({"version": 99}) is None
    assert chapters_from_payload({"version": 1, "chapters": [{"bad": True}]}) is None


# --- detection wiring -----------------------------------------------------------


def _deck_doc(session: Session, tmp_path: Path, *, file_hash: str) -> Document:
    # Headingless markdown → Tier 2 yields needs_manual → Tier 3 (deck) runs.
    md = tmp_path / f"{file_hash}.md"
    md.write_text("plain slide text with no headings\n", encoding="utf-8")
    subject = Subject(name="Physics")
    session.add(subject)
    session.commit()
    document = Document(
        subject_id=subject.id,
        filename="deck.pdf",
        file_hash=file_hash,
        markdown_path=str(md),
    )
    session.add(document)
    session.commit()
    return document


def _heuristic_deck() -> ProposedStructure:
    """What extract_pdf_structure returns for a flat deck (slides attached)."""
    chapters = [
        ProposedChapter(
            title="Slides",
            order_index=0,
            topics=[
                ProposedTopic(title=t, order_index=i, pages=pages)
                for i, (t, pages) in enumerate(SLIDES)
            ],
        )
    ]
    return ProposedStructure(
        chapters=chapters, needs_manual=False, method="pdf_headings", slides=SLIDES
    )


def _grouped_chapters() -> list[ProposedChapter]:
    titles, groups = parse_slide_grouping(_GROUPING, slide_count=6)
    return build_grouped_chapters(titles, groups, SLIDES)


def test_detect_uses_grouper_and_caches(session: Session, tmp_path: Path) -> None:
    document = _deck_doc(session, tmp_path, file_hash="deck1")
    (tmp_path / "deck1.pdf").write_bytes(b"%PDF-1.4 fake")
    calls = {"n": 0}

    def grouper(slides):
        calls["n"] += 1
        assert slides == SLIDES
        return _grouped_chapters()

    kwargs = {
        "pdf_outline_fn": lambda _p: _heuristic_deck(),
        "outline_reader": lambda _p: (None, 7),
        "uploads_dir": tmp_path,
        "cache_root": tmp_path / "cache",
    }
    structure = docsvc.detect_for_document(
        session, document.id, slide_grouper=grouper, **kwargs
    )
    assert structure.method == "ai_grouping"
    assert structure.has_headings is True
    assert [c.title for c in structure.chapters] == ["Rolling motion", "Rotation"]
    assert (tmp_path / "cache" / "deck1" / "slide_grouping.json").is_file()

    # Second detection: served from the cache, the grouper is never called again.
    def exploding(_slides):
        raise AssertionError("must not re-pay the grouping call")

    again = docsvc.detect_for_document(
        session, document.id, slide_grouper=exploding, **kwargs
    )
    assert calls["n"] == 1
    assert [c.title for c in again.chapters] == ["Rolling motion", "Rotation"]


def test_detect_falls_back_to_heuristic_when_grouper_fails(
    session: Session, tmp_path: Path
) -> None:
    document = _deck_doc(session, tmp_path, file_hash="deck2")
    (tmp_path / "deck2.pdf").write_bytes(b"%PDF-1.4 fake")

    def failing(_slides):
        raise RuntimeError("no provider headroom")

    structure = docsvc.detect_for_document(
        session,
        document.id,
        pdf_outline_fn=lambda _p: _heuristic_deck(),
        outline_reader=lambda _p: (None, 7),
        uploads_dir=tmp_path,
        slide_grouper=failing,
        cache_root=tmp_path / "cache",
    )
    # The heuristic tree stands, flagged for order-sensitive review as before.
    assert structure.method == "pdf_headings"
    assert structure.has_headings is False
    assert [c.title for c in structure.chapters] == ["Slides"]


def test_detect_skips_grouping_for_small_decks(
    session: Session, tmp_path: Path
) -> None:
    document = _deck_doc(session, tmp_path, file_hash="deck3")
    (tmp_path / "deck3.pdf").write_bytes(b"%PDF-1.4 fake")
    small = _heuristic_deck()
    small.slides = SLIDES[:3]  # below MIN_SLIDES_FOR_GROUPING

    structure = docsvc.detect_for_document(
        session,
        document.id,
        pdf_outline_fn=lambda _p: small,
        outline_reader=lambda _p: (None, 3),
        uploads_dir=tmp_path,
        slide_grouper=lambda _s: (_ for _ in ()).throw(AssertionError("not worth a call")),
        cache_root=tmp_path / "cache",
    )
    assert structure.method == "pdf_headings"


# --- pages persist through confirm and drive source slicing --------------------


def test_confirm_persists_topic_pages(session: Session, tmp_path: Path) -> None:
    document = _deck_doc(session, tmp_path, file_hash="deck4")
    docsvc.confirm_structure(
        session,
        document.id,
        chapters=[
            ChapterIn(
                title="Rolling motion",
                topics=[
                    TopicIn(title="Rolling dynamics", pages=[3, 1, 2, 2]),
                    TopicIn(title="Manual addition"),  # no pages → None
                ],
            )
        ],
    )
    topics = session.query(Topic).order_by(Topic.order_index).all()
    assert topics[0].pdf_pages == [1, 2, 3]  # sorted, de-duplicated
    assert topics[1].pdf_pages is None


def test_get_pages_markdown_converts_runs_and_caches(tmp_path: Path) -> None:
    fitz = __import__("fitz")
    pdf = tmp_path / "deck.pdf"
    doc = fitz.open()
    for i in range(9):
        doc.new_page().insert_text((72, 72), f"Page {i + 1}")
    doc.save(str(pdf))
    doc.close()

    runs: list[int] = []

    def spy(sub_pdf: Path) -> str:
        with fitz.open(str(sub_pdf)) as d:
            runs.append(d.page_count)
        return f"RUN({runs[-1]})"

    cache_root = tmp_path / "cache"
    out = get_pages_markdown(
        pdf, "h", [4, 3, 9, 3], cache_root=cache_root, converter=spy
    )
    # Converted per page (duplicates collapsed), cached per page.
    assert runs == [1, 1, 1]
    assert out == "RUN(1)\n\nRUN(1)\n\nRUN(1)"
    for page in (3, 4, 9):
        assert (cache_root / "h" / "page-md" / f"p{page}.md").is_file()

    # Cached: the converter is not called again for any union of those pages.
    again = get_pages_markdown(
        pdf, "h", [3, 4, 9], cache_root=cache_root, converter=spy
    )
    assert runs == [1, 1, 1]
    assert again == out


def test_load_topic_source_prefers_pdf_pages(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("whole document markdown", encoding="utf-8")
    subject = Subject(name="Physics")
    document = Document(
        subject=subject, filename="deck.pdf", file_hash="hh", markdown_path=str(md)
    )
    chapter = Chapter(document=document, subject=subject, title="Slides")
    topic = Topic(chapter=chapter, title="Rolling dynamics", pdf_pages=[2, 3])
    session.add_all([subject, document, chapter, topic])
    session.commit()

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "hh.pdf").write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(generation, "UPLOADS_DIR", uploads)

    seen: dict = {}

    def fake_pages_md(pdf_path, file_hash, pages):
        seen["args"] = (Path(pdf_path).name, file_hash, pages)
        return "EXACT SLIDE TEXT"

    monkeypatch.setattr(generation, "get_pages_markdown", fake_pages_md)

    assert generation.load_topic_source(session, topic) == "EXACT SLIDE TEXT"
    assert seen["args"] == ("hh.pdf", "hh", [2, 3])


def test_load_topic_source_falls_back_when_pdf_missing(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    md = tmp_path / "doc.md"
    md.write_text("whole document markdown", encoding="utf-8")
    subject = Subject(name="Physics")
    document = Document(
        subject=subject, filename="deck.pdf", file_hash="gone", markdown_path=str(md)
    )
    chapter = Chapter(document=document, subject=subject, title="Slides")
    topic = Topic(chapter=chapter, title="Rolling", pdf_pages=[1])
    session.add_all([subject, document, chapter, topic])
    session.commit()

    monkeypatch.setattr(generation, "UPLOADS_DIR", tmp_path / "empty-uploads")
    # No heading matches "Rolling" → single-topic proportional slice = whole doc.
    assert generation.load_topic_source(session, topic) == "whole document markdown"
