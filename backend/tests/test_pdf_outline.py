"""PDF-outline fallback tests (Stage 2 recovery for header-less PDFs).

markitdown emits no ATX headings for slide decks / lecture PDFs, so the markdown
detector returns ``needs_manual``. These prove the free PyMuPDF fallback recovers
real structure from the embedded outline (bookmarks) and, failing that, font
sizes — using real fixture PDFs built with PyMuPDF (a hard project dep).

A presentation (flat list of slide titles) collapses into a single chapter with
each slide as a topic; a book or a deck with named sections (hierarchical, or
"Chapter N" lines) keeps the chapter→topic tree.
"""

from __future__ import annotations

from pathlib import Path

from backend.services.pipeline.pdf_outline import extract_pdf_structure


def _make_pdf(
    path: Path,
    pages: list[list[tuple[str, float]]],
    *,
    toc=None,
    title: str | None = None,
) -> Path:
    """Write a PDF: ``pages`` is per-page ``(text, fontsize)`` spans; optional TOC."""
    fitz = __import__("fitz")  # PyMuPDF
    doc = fitz.open()
    for spans in pages:
        page = doc.new_page()
        y = 72.0
        for text, size in spans:
            page.insert_text((72, y), text, fontsize=size)
            y += size + 10
    if title is not None:
        doc.set_metadata({"title": title})
    if toc is not None:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return path


# --- flat slide decks → one chapter, slides as topics -----------------------


def test_flat_outline_becomes_one_chapter_of_slides(tmp_path: Path) -> None:
    pdf = _make_pdf(
        tmp_path / "deck.pdf",
        pages=[[("body", 11)]] * 3,
        toc=[
            [1, "Slide 1", 1],  # generic prefix, no title → dropped
            [1, "Slide 2: Rolling motion", 2],
            [1, "Slide 3: Angular momentum", 3],
        ],
        title="Mechanics Lecture",
    )
    structure = extract_pdf_structure(pdf)
    assert structure is not None
    assert structure.method == "pdf_outline"
    assert structure.needs_manual is False
    # One unit named from the file; each slide is a topic.
    assert [c.title for c in structure.chapters] == ["Mechanics Lecture"]
    assert [t.title for t in structure.chapters[0].topics] == [
        "Rolling motion",
        "Angular momentum",
    ]


def test_generic_outline_falls_through_to_font_sizes(tmp_path: Path) -> None:
    body = ("normal body text that carries most of the characters", 10)
    pdf = _make_pdf(
        tmp_path / "deck.pdf",
        pages=[
            [("Introduction to Forces", 24), body, body],
            [("Conservation Laws", 24), body, body],
        ],
        toc=[[1, "Diapositiva 1", 1], [1, "Diapositiva 2", 2]],  # all generic
        title="Presentazione standard di PowerPoint",  # generic → rejected
    )
    structure = extract_pdf_structure(pdf)
    assert structure is not None
    assert structure.method == "pdf_headings"
    # Generic metadata title rejected → neutral deck label, slides as topics.
    assert [c.title for c in structure.chapters] == ["Slides"]
    assert [t.title for t in structure.chapters[0].topics] == [
        "Introduction to Forces",
        "Conservation Laws",
    ]


def test_font_headings_collapse_repeated_titles(tmp_path: Path) -> None:
    body = ("normal body text that carries most of the characters", 10)
    pdf = _make_pdf(
        tmp_path / "deck.pdf",
        pages=[
            [("Rolling down a ramp", 24), body, body],
            [("Rolling down a ramp", 24), body, body],  # continuation slide
            [("Yo-yo example", 24), body, body],
        ],
    )
    structure = extract_pdf_structure(pdf)
    assert structure is not None
    assert [c.title for c in structure.chapters] == ["Slides"]
    assert [t.title for t in structure.chapters[0].topics] == [
        "Rolling down a ramp",
        "Yo-yo example",
    ]


def test_related_consecutive_slides_merge(tmp_path: Path) -> None:
    # Slides continuing the same subject fold into one topic; a different subject
    # starts a new one.
    body = ("normal body text that carries most of the characters", 10)
    pdf = _make_pdf(
        tmp_path / "deck.pdf",
        pages=[
            [("Forces and Kinetic energy of rolling", 24), body, body],
            [("Forces of rolling", 24), body, body],  # same subject → merged
            [("Angular momentum", 24), body, body],  # new subject → separate
        ],
    )
    structure = extract_pdf_structure(pdf)
    assert structure is not None
    assert [t.title for t in structure.chapters[0].topics] == [
        "Forces and Kinetic energy of rolling",
        "Angular momentum",
    ]


def test_merge_run_is_capped(tmp_path: Path) -> None:
    # A word recurring across many slides must not fuse a whole section into one
    # topic — the run caps so the section stays splittable.
    body = ("normal body text that carries most of the characters", 10)
    pdf = _make_pdf(
        tmp_path / "deck.pdf",
        pages=[
            [(f"Rolling motion case {word}", 24), body, body]
            for word in ("alpha", "beta", "gamma", "delta", "epsilon")
        ],
    )
    structure = extract_pdf_structure(pdf)
    assert structure is not None
    # Five same-subject slides, run capped at 3 → 2 topics, not 1.
    assert len(structure.chapters[0].topics) == 2


# --- books / decks with real hierarchy → chapter tree -----------------------


def test_named_sections_become_chapters(tmp_path: Path) -> None:
    pdf = _make_pdf(
        tmp_path / "deck.pdf",
        pages=[[("body", 11)]] * 3,
        toc=[
            [1, "Kinematics", 1],
            [2, "Velocity", 1],
            [2, "Acceleration", 2],
            [1, "Dynamics", 3],
            [2, "Newton's laws", 3],
        ],
    )
    structure = extract_pdf_structure(pdf)
    assert structure is not None
    # Hierarchy present → sections are chapters, slides are topics.
    assert [c.title for c in structure.chapters] == ["Kinematics", "Dynamics"]
    assert [t.title for t in structure.chapters[0].topics] == ["Velocity", "Acceleration"]
    assert [t.title for t in structure.chapters[1].topics] == ["Newton's laws"]


def test_flat_chapter_headings_stay_chapters(tmp_path: Path) -> None:
    # A book whose outline is flat but plainly chaptered must not be flattened
    # into a single unit the way a slide deck is.
    pdf = _make_pdf(
        tmp_path / "book.pdf",
        pages=[[("body", 11)]] * 3,
        toc=[
            [1, "Chapter 1: Foundations", 1],
            [1, "Chapter 2: Methods", 2],
            [1, "Chapter 3: Results", 3],
        ],
    )
    structure = extract_pdf_structure(pdf)
    assert structure is not None
    assert [c.title for c in structure.chapters] == [
        "Chapter 1: Foundations",
        "Chapter 2: Methods",
        "Chapter 3: Results",
    ]


# --- nothing to recover ------------------------------------------------------


def test_no_structure_returns_none(tmp_path: Path) -> None:
    # Uniform body text, no outline, no larger-font lines → nothing to propose.
    body = ("just one size of plain prose with nothing that looks like a title", 11)
    pdf = _make_pdf(tmp_path / "flat.pdf", pages=[[body, body, body]])
    assert extract_pdf_structure(pdf) is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert extract_pdf_structure(tmp_path / "does-not-exist.pdf") is None
