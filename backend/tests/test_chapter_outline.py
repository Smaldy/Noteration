"""Chapter Lanes & Lazy Ingestion — Wave 2.

Outline extraction (``read_toc`` + ``IngestionResult.outline``), the deterministic
trash filter, TOC → chapter slicing, and ``detect_for_document``'s outline-primary
tier. Fixture PDFs are built with PyMuPDF (a hard project dep), mirroring
test_pdf_outline.py.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from backend.models import Document, Subject
from backend.models.enums import TopicPriority
from backend.services import documents as docsvc
from backend.services.pipeline.ingestion import ingest, read_toc
from backend.services.pipeline.pdf_outline import (
    extract_chapters_from_toc,
    is_trash,
)


def _stub_render(_pdf: Path, out_dir: Path, _dpi: int) -> list[Path]:
    """Stand-in renderer: creates the staging dir (as the real one does), no pages."""
    out_dir.mkdir(parents=True, exist_ok=True)
    return []


def _make_toc_pdf(path: Path, toc, page_count: int) -> Path:
    """Write a PDF of ``page_count`` blank-ish pages with an embedded TOC."""
    fitz = __import__("fitz")  # PyMuPDF
    doc = fitz.open()
    for _ in range(page_count):
        page = doc.new_page()
        page.insert_text((72, 72), "body text")
    doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return path


# --- trash filter -----------------------------------------------------------


def test_is_trash_is_case_insensitive_strip_match() -> None:
    assert is_trash("  Index ") is True
    assert is_trash("INDEX") is True
    assert is_trash("Copyright") is True
    assert is_trash("Chapter 1: Index Structures") is False
    assert is_trash("Routing") is False


# --- TOC → chapter slices ---------------------------------------------------


def test_extract_chapters_from_toc_real_book() -> None:
    # Cover, Copyright, Chapter 1..8, References, Index — a real-looking TOC.
    outline = [(1, "Cover", 1), (1, "Copyright", 2)]
    page = 5
    for n in range(1, 9):
        outline.append((1, f"Chapter {n}", page))
        page += 30
    outline.append((1, "References", page))
    outline.append((1, "Index", page + 10))
    total_pages = page + 20
    by_title = {s.title: s for s in extract_chapters_from_toc(outline, total_pages)}

    # Trash front/back matter is auto-skipped; real chapters are not.
    assert by_title["Cover"].auto_skip is True  # single page 1..1
    assert by_title["Copyright"].auto_skip is True  # trash title
    assert by_title["References"].auto_skip is True
    assert by_title["Index"].auto_skip is True
    for n in range(1, 9):
        assert by_title[f"Chapter {n}"].auto_skip is False

    # Page ranges: Chapter 1 runs 5..34 (next chapter starts at 35).
    assert (by_title["Chapter 1"].page_start, by_title["Chapter 1"].page_end) == (5, 34)
    assert by_title["Chapter 2"].page_start == 35
    # Last entry (Index) runs to total_pages.
    assert by_title["Index"].page_end == total_pages
    # Copyright runs 2..4 (Chapter 1 starts at 5).
    assert (by_title["Copyright"].page_start, by_title["Copyright"].page_end) == (2, 4)


def test_extract_chapters_filters_to_level_1_for_page_end() -> None:
    # Level-2 entries are dropped, and page_end uses the next *level-1* start.
    outline = [
        (1, "Chapter 1", 1),
        (2, "1.1 Section", 3),  # excluded; must not shorten Chapter 1's range
        (2, "1.2 Section", 6),
        (1, "Chapter 2", 10),
    ]
    slices = extract_chapters_from_toc(outline, total_pages=20)
    assert [s.title for s in slices] == ["Chapter 1", "Chapter 2"]
    assert (slices[0].page_start, slices[0].page_end) == (1, 9)
    assert (slices[1].page_start, slices[1].page_end) == (10, 20)


# --- read_toc + IngestionResult.outline -------------------------------------


def test_read_toc_none_below_min_entries(tmp_path: Path) -> None:
    pdf = _make_toc_pdf(tmp_path / "thin.pdf", toc=[[1, "Only", 1]], page_count=3)
    outline, total_pages = read_toc(pdf)
    assert outline is None
    assert total_pages == 3


def test_read_toc_present_for_real_outline(tmp_path: Path) -> None:
    toc = [[1, "Chapter 1", 1], [1, "Chapter 2", 2], [1, "Chapter 3", 3]]
    pdf = _make_toc_pdf(tmp_path / "book.pdf", toc=toc, page_count=4)
    outline, total_pages = read_toc(pdf)
    assert outline is not None
    assert [t for _, t, _ in outline] == ["Chapter 1", "Chapter 2", "Chapter 3"]
    assert total_pages == 4


def test_ingest_stamps_outline_without_calling_converter_for_it(tmp_path: Path) -> None:
    # Single-entry TOC → IngestionResult.outline is None.
    pdf = _make_toc_pdf(tmp_path / "thin.pdf", toc=[[1, "Only", 1]], page_count=2)
    result = ingest(
        pdf,
        cache_root=tmp_path / "cache",
        convert=lambda _p: "stub markdown",
        render=_stub_render,
    )
    assert result.outline is None

    # A real (≥3 entry) outline is carried on the result.
    book = _make_toc_pdf(
        tmp_path / "book.pdf",
        toc=[[1, "Ch 1", 1], [1, "Ch 2", 2], [1, "Ch 3", 3]],
        page_count=3,
    )
    book_result = ingest(
        book,
        cache_root=tmp_path / "cache",
        convert=lambda _p: "stub markdown",
        render=_stub_render,
    )
    assert book_result.outline is not None
    assert len(book_result.outline) == 3


# --- detect_for_document outline tier ---------------------------------------


def _doc(session: Session, tmp_path: Path, *, markdown: str, file_hash: str) -> Document:
    md = tmp_path / f"{file_hash}.md"
    md.write_text(markdown, encoding="utf-8")
    subject = Subject(name="Networking")
    session.add(subject)
    session.commit()
    document = Document(
        subject_id=subject.id,
        filename="book.pdf",
        file_hash=file_hash,
        markdown_path=str(md),
    )
    session.add(document)
    session.commit()
    return document


def test_detect_uses_outline_path_over_markdown(session: Session, tmp_path: Path) -> None:
    # Markdown HAS headings, but an outline exists → the outline (with page ranges)
    # wins, because markdown headings carry no page mapping. Trash front/back matter
    # (Cover, Index) is dropped entirely — not proposed even as a skip topic.
    document = _doc(session, tmp_path, markdown="# Ignored\n# AlsoIgnored\n", file_hash="bk")
    (tmp_path / "bk.pdf").write_bytes(b"%PDF-1.4 fake")
    outline = [(1, "Cover", 1), (1, "Chapter 1", 2), (1, "Index", 10)]

    structure = docsvc.detect_for_document(
        session,
        document.id,
        outline_reader=lambda _p: (outline, 12),
        uploads_dir=tmp_path,
    )

    assert structure.method == "pdf_outline"
    assert structure.needs_manual is False
    # Cover + Index are trash → gone; only the real chapter remains, with its page
    # range intact (the multi-page Index still let _looks_like_book see a book).
    assert [c.title for c in structure.chapters] == ["Chapter 1"]
    chapter_one = structure.chapters[0]
    assert (chapter_one.page_start, chapter_one.page_end) == (2, 9)
    assert chapter_one.topics[0].priority is TopicPriority.medium


def test_detect_skips_outline_for_bookmarked_slide_deck(
    session: Session, tmp_path: Path
) -> None:
    # A deck exported with per-slide bookmarks has a TOC, but every entry is a
    # single page → no real chapter structure → must NOT take the outline tier
    # (it would yield N one-page, all-skipped chapters). Falls to markdown/slides.
    document = _doc(session, tmp_path, markdown="# A\n# B\n", file_hash="dk")
    (tmp_path / "dk.pdf").write_bytes(b"%PDF-1.4 fake")
    deck_outline = [(1, "Slide 1", 1), (1, "Slide 2", 2), (1, "Slide 3", 3)]

    structure = docsvc.detect_for_document(
        session,
        document.id,
        outline_reader=lambda _p: (deck_outline, 3),
        uploads_dir=tmp_path,
    )

    assert structure.method == "markdown"
    assert [c.title for c in structure.chapters] == ["A", "B"]


def test_detect_falls_back_to_markdown_when_no_outline(
    session: Session, tmp_path: Path
) -> None:
    document = _doc(session, tmp_path, markdown="# A\n# B\n", file_hash="md")
    (tmp_path / "md.pdf").write_bytes(b"%PDF-1.4 fake")

    structure = docsvc.detect_for_document(
        session,
        document.id,
        outline_reader=lambda _p: (None, 5),
        uploads_dir=tmp_path,
    )

    assert structure.method == "markdown"
    assert [c.title for c in structure.chapters] == ["A", "B"]
