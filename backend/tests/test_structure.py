"""Structure detection tests (Phase 6a) — pure markdown → proposed tree."""

from __future__ import annotations

from backend.services.pipeline.structure import detect_structure


def _titles(chapter):
    return [t.title for t in chapter.topics]


def test_two_level_markdown_maps_to_chapters_and_topics() -> None:
    md = """# Chapter A

## Topic A1
body
## Topic A2

# Chapter B

## Topic B1
"""
    s = detect_structure(md)

    assert s.needs_manual is False
    assert s.method == "markdown"
    assert s.has_headings is True
    assert [c.title for c in s.chapters] == ["Chapter A", "Chapter B"]
    assert _titles(s.chapters[0]) == ["Topic A1", "Topic A2"]
    assert _titles(s.chapters[1]) == ["Topic B1"]
    # order_index is contiguous per level
    assert [c.order_index for c in s.chapters] == [0, 1]
    assert [t.order_index for t in s.chapters[0].topics] == [0, 1]


def test_chapter_without_subheadings_gets_default_topic() -> None:
    # Two levels exist, but Chapter B has no topics of its own.
    md = "# Chapter A\n## Topic A1\n# Chapter B\n"
    s = detect_structure(md)

    assert _titles(s.chapters[0]) == ["Topic A1"]
    assert _titles(s.chapters[1]) == ["Chapter B"]  # defaulted to chapter title


def test_single_level_headings_each_become_a_chapter() -> None:
    md = "# Kinematics\n# Dynamics\n# Thermodynamics\n"
    s = detect_structure(md)

    assert [c.title for c in s.chapters] == ["Kinematics", "Dynamics", "Thermodynamics"]
    # each is guaranteed one processable topic (its own title)
    assert all(_titles(c) == [c.title] for c in s.chapters)


def test_deeper_levels_flatten_into_topics() -> None:
    md = "# A\n## t1\n### t2\n#### t3\n"
    s = detect_structure(md)

    assert len(s.chapters) == 1
    assert _titles(s.chapters[0]) == ["t1", "t2", "t3"]


def test_topic_before_first_chapter_gets_synthetic_chapter() -> None:
    md = "## Orphan intro\n# Real Chapter\n## Real Topic\n"
    s = detect_structure(md)

    assert [c.title for c in s.chapters] == ["Chapter 1", "Real Chapter"]
    assert _titles(s.chapters[0]) == ["Orphan intro"]
    assert _titles(s.chapters[1]) == ["Real Topic"]


def test_headings_inside_code_fences_are_ignored() -> None:
    md = "# Real\n\n```\n# fake heading in code\n```\n\n## Topic\n"
    s = detect_structure(md)

    assert [c.title for c in s.chapters] == ["Real"]
    assert _titles(s.chapters[0]) == ["Topic"]


def test_titles_are_cleaned() -> None:
    md = "#   Spaced   Title   ###\n## **Bold Topic**\n"
    s = detect_structure(md)

    assert s.chapters[0].title == "Spaced Title"
    assert _titles(s.chapters[0]) == ["Bold Topic"]


def test_text_fallback_detects_chapter_lines() -> None:
    md = "Chapter 1: Introduction\n\nsome body text\n\nChapter 2 - Methods\n"
    s = detect_structure(md)

    assert s.method == "text"
    assert s.needs_manual is False
    # Text-fallback chapters are not ATX headings, so notes can't slice by them.
    assert s.has_headings is False
    assert [c.title for c in s.chapters] == ["Chapter 1: Introduction", "Chapter 2 - Methods"]
    assert all(len(c.topics) == 1 for c in s.chapters)


def test_roman_numeral_chapters_in_text_fallback() -> None:
    md = "Part IV: Electromagnetism\n\nbody\n\nPart V: Optics\n"
    s = detect_structure(md)

    assert s.method == "text"
    assert [c.title for c in s.chapters] == ["Part IV: Electromagnetism", "Part V: Optics"]


def test_no_headings_flags_manual_fallback() -> None:
    md = "Just some flowing prose with no structure at all.\nAnother line.\n"
    s = detect_structure(md)

    assert s.needs_manual is True
    assert s.method == "manual"
    assert s.has_headings is False
    assert s.chapters == []


def test_empty_markdown_flags_manual() -> None:
    s = detect_structure("")
    assert s.needs_manual is True
    assert s.chapters == []
