"""PDF-outline fallback tests (Stage 2 recovery for header-less PDFs).

markitdown emits no ATX headings for slide decks / lecture PDFs, so the markdown
detector returns ``needs_manual``. These prove the free PyMuPDF fallback recovers
real structure from the embedded outline (bookmarks) and, failing that, font
sizes — using real fixture PDFs built with PyMuPDF (a hard project dep).
"""

from __future__ import annotations

from pathlib import Path

from backend.services.pipeline.pdf_outline import extract_pdf_structure


def _make_pdf(path: Path, pages: list[list[tuple[str, float]]], toc=None) -> Path:
    """Write a PDF: ``pages`` is per-page ``(text, fontsize)`` spans; optional TOC."""
    fitz = __import__("fitz")  # PyMuPDF
    doc = fitz.open()
    for spans in pages:
        page = doc.new_page()
        y = 72.0
        for text, size in spans:
            page.insert_text((72, y), text, fontsize=size)
            y += size + 10
    if toc is not None:
        doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return path


def test_extract_uses_embedded_outline(tmp_path: Path) -> None:
    pdf = _make_pdf(
        tmp_path / "deck.pdf",
        pages=[[("body", 11)]] * 3,
        toc=[
            [1, "Slide 1", 1],  # generic prefix, no title → dropped
            [1, "Slide 2: Rolling motion", 2],
            [1, "Slide 3: Angular momentum", 3],
        ],
    )
    structure = extract_pdf_structure(pdf)
    assert structure is not None
    assert structure.method == "pdf_outline"
    assert structure.needs_manual is False
    titles = [c.title for c in structure.chapters]
    assert titles == ["Rolling motion", "Angular momentum"]
    # Every chapter is a processable unit (≥1 topic), matching the markdown path.
    assert all(c.topics for c in structure.chapters)


def test_generic_outline_falls_through_to_font_sizes(tmp_path: Path) -> None:
    body = ("normal body text that carries most of the characters", 10)
    pdf = _make_pdf(
        tmp_path / "deck.pdf",
        pages=[
            [("Introduction to Forces", 24), body, body],
            [("Conservation Laws", 24), body, body],
        ],
        toc=[[1, "Diapositiva 1", 1], [1, "Diapositiva 2", 2]],  # all generic
    )
    structure = extract_pdf_structure(pdf)
    assert structure is not None
    assert structure.method == "pdf_headings"
    assert [c.title for c in structure.chapters] == [
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
    assert [c.title for c in structure.chapters] == [
        "Rolling down a ramp",
        "Yo-yo example",
    ]


def test_no_structure_returns_none(tmp_path: Path) -> None:
    # Uniform body text, no outline, no larger-font lines → nothing to propose.
    body = ("just one size of plain prose with nothing that looks like a title", 11)
    pdf = _make_pdf(tmp_path / "flat.pdf", pages=[[body, body, body]])
    assert extract_pdf_structure(pdf) is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert extract_pdf_structure(tmp_path / "does-not-exist.pdf") is None
