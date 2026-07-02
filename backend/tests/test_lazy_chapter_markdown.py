"""Chapter Lanes & Lazy Ingestion — Wave 4.

Lazy per-chapter markdown: ``get_chapter_markdown`` (cache hit/miss + page-range
extraction) and ``load_topic_source`` routing (outline chapter → chapter markdown;
no page range → existing whole-doc path). Fixture PDFs are built with PyMuPDF.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.services.pipeline import generation
from backend.services.pipeline.ingestion import get_chapter_markdown, ingest


def _make_toc_pdf(path: Path, pages: int, toc) -> Path:
    fitz = __import__("fitz")  # PyMuPDF
    doc = fitz.open()
    for i in range(pages):
        doc.new_page().insert_text((72, 72), f"Page {i + 1}")
    doc.set_toc(toc)
    doc.save(str(path))
    doc.close()
    return path


def _fake_render(n: int):
    def render(_pdf: Path, out_dir: Path, _dpi: int) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for i in range(n):
            p = out_dir / f"page-{i + 1:05d}.png"
            p.write_bytes(b"x")
            paths.append(p)
        return paths

    return render


def _make_pdf(path: Path, pages: int) -> Path:
    fitz = __import__("fitz")  # PyMuPDF
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1} content")
    doc.save(str(path))
    doc.close()
    return path


# --- get_chapter_markdown ---------------------------------------------------


def test_cache_hit_returns_cached_without_converter(tmp_path: Path) -> None:
    cache_root = tmp_path / "cache"
    chapters_dir = cache_root / "h" / "chapters"
    chapters_dir.mkdir(parents=True)
    (chapters_dir / "p1-5.md").write_text("CACHED CONTENT", encoding="utf-8")

    calls: list[Path] = []

    def spy(p: Path) -> str:
        calls.append(p)
        return "FRESH"

    out = get_chapter_markdown(
        tmp_path / "missing.pdf", "h", 1, 5, cache_root=cache_root, converter=spy
    )
    assert out == "CACHED CONTENT"
    assert calls == []  # converter never touched on a hit


def test_cache_miss_converts_page_range_and_writes_cache(tmp_path: Path) -> None:
    pdf = _make_pdf(tmp_path / "book.pdf", pages=10)
    cache_root = tmp_path / "cache"
    seen: dict[str, int] = {}

    def spy(sub_pdf: Path) -> str:
        fitz = __import__("fitz")
        with fitz.open(str(sub_pdf)) as d:
            seen["pages"] = d.page_count
        return "CHAPTER MARKDOWN"

    out = get_chapter_markdown(
        pdf, "hh", 3, 6, cache_root=cache_root, converter=spy
    )
    assert out == "CHAPTER MARKDOWN"
    # Pages 3..6 inclusive → a 4-page sub-PDF was handed to the converter.
    assert seen["pages"] == 4
    # Result cached for next time at chapters/p<start>-<end>.md.
    cached = (cache_root / "hh" / "chapters" / "p3-6.md").read_text(encoding="utf-8")
    assert cached == "CHAPTER MARKDOWN"


def test_chapter_slice_is_small_fraction_of_full_doc(tmp_path: Path) -> None:
    # Token-reduction proof: a 60-page chapter is a small fraction of a 500-page
    # book once converted, where the converter output scales with page count.
    pdf = _make_pdf(tmp_path / "big.pdf", pages=500)
    cache_root = tmp_path / "cache"

    def proportional(sub_pdf: Path) -> str:
        fitz = __import__("fitz")
        with fitz.open(str(sub_pdf)) as d:
            return "x" * (d.page_count * 200)

    full = get_chapter_markdown(
        pdf, "full", 1, 500, cache_root=cache_root, converter=proportional
    )
    chapter = get_chapter_markdown(
        pdf, "chap", 100, 159, cache_root=cache_root, converter=proportional
    )
    assert len(chapter) < 0.15 * len(full)  # 60 / 500 = 12%


# --- book-mode: skip whole-document markitdown ------------------------------


def test_large_book_skips_markitdown(tmp_path: Path) -> None:
    # 90 pages with 3 multi-page chapters → outline-backed book → markdown skipped.
    pdf = _make_toc_pdf(
        tmp_path / "book.pdf",
        pages=90,
        toc=[[1, "Chapter 1", 1], [1, "Chapter 2", 40], [1, "Chapter 3", 70]],
    )
    calls: list[Path] = []

    def spy(p: Path) -> str:
        calls.append(p)
        return "WHOLE DOC MARKDOWN"

    result = ingest(
        pdf, cache_root=tmp_path / "cache", convert=spy, render=_fake_render(90)
    )
    assert result.book_mode is True
    assert result.markdown_path is None
    assert calls == []  # markitdown never ran for the whole book


def test_short_deck_still_runs_markitdown(tmp_path: Path) -> None:
    pdf = _make_toc_pdf(
        tmp_path / "deck.pdf",
        pages=20,
        toc=[[1, "S1", 1], [1, "S2", 8], [1, "S3", 15]],
    )
    calls: list[Path] = []

    def spy(p: Path) -> str:
        calls.append(p)
        return "# Deck\n\ncontent"

    result = ingest(
        pdf, cache_root=tmp_path / "cache", convert=spy, render=_fake_render(20)
    )
    assert result.book_mode is False
    assert result.markdown_path is not None
    assert len(calls) == 1


def test_long_bookmarked_deck_is_not_book_mode(tmp_path: Path) -> None:
    # >80 pages, but every TOC entry is a single page (a bookmarked slide deck):
    # NOT a book, so markdown must still be built (else detection would have none).
    toc = [[1, f"Slide {i}", i] for i in range(1, 91)]
    pdf = _make_toc_pdf(tmp_path / "longdeck.pdf", pages=90, toc=toc)
    calls: list[Path] = []

    def spy(p: Path) -> str:
        calls.append(p)
        return "slide text"

    result = ingest(
        pdf, cache_root=tmp_path / "cache", convert=spy, render=_fake_render(90)
    )
    assert result.book_mode is False
    assert len(calls) == 1


# --- load_topic_source routing ---------------------------------------------


def test_load_topic_source_uses_chapter_markdown_for_outline_chapter(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    subject = Subject(name="Networking")
    whole = tmp_path / "whole.md"
    whole.write_text("# Routing\n\nWHOLE-DOC text must not be used.\n", encoding="utf-8")
    document = Document(
        subject=subject, filename="b.pdf", file_hash="bk", markdown_path=str(whole)
    )
    chapter = Chapter(
        document=document,
        subject=subject,
        title="Chapter 3",
        order_index=2,
        page_start=12,
        page_end=79,
    )
    topic = Topic(chapter=chapter, title="Routing", order_index=0)
    session.add(topic)
    session.commit()

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / "bk.pdf").write_bytes(b"%PDF-1.4 fake")
    monkeypatch.setattr(generation, "UPLOADS_DIR", uploads)

    captured: dict[str, object] = {}

    def fake_chapter_md(pdf_path, file_hash, page_start, page_end, **_kw):
        captured.update(file_hash=file_hash, ps=page_start, pe=page_end)
        return "# Routing\n\nRouting tables and forwarding decisions.\n"

    monkeypatch.setattr(generation, "get_chapter_markdown", fake_chapter_md)

    source = generation.load_topic_source(session, topic)
    assert "Routing tables" in source
    assert "WHOLE-DOC" not in source
    assert captured == {"file_hash": "bk", "ps": 12, "pe": 79}


def test_load_topic_source_without_page_start_uses_whole_doc(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    # Slide deck / headingless: no page range → existing whole-doc path, and the
    # lazy chapter-markdown path must NOT run (regression guard).
    subject = Subject(name="Deck")
    md = tmp_path / "deck.md"
    md.write_text("# Intro\n\nslide content here\n", encoding="utf-8")
    document = Document(
        subject=subject, filename="s.pdf", file_hash="dk", markdown_path=str(md)
    )
    chapter = Chapter(document=document, subject=subject, title="Slides", order_index=0)
    topic = Topic(chapter=chapter, title="Intro", order_index=0)
    session.add(topic)
    session.commit()

    def boom(*_a, **_k):
        raise AssertionError("chapter markdown must not run without a page range")

    monkeypatch.setattr(generation, "get_chapter_markdown", boom)

    source = generation.load_topic_source(session, topic)
    assert "slide content here" in source
