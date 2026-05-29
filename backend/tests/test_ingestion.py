"""Ingestion stage tests (Phase 5).

Most tests inject fake converter/renderer so the caching + orchestration logic
is exercised deterministically without markitdown/PyMuPDF. One end-to-end test
generates a real PDF (via PyMuPDF) and runs the real backends.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from backend.services.pipeline.ingestion import (
    IngestionResult,
    compute_file_hash,
    ingest,
)


def _write_pdf_bytes(path: Path, payload: bytes = b"%PDF-1.4 fake bytes\n") -> Path:
    """A stand-in 'PDF' file — only its bytes matter for hashing in fake tests."""
    path.write_bytes(payload)
    return path


def _fake_render_factory(page_count: int):
    """Return a renderer that writes ``page_count`` 1-byte PNGs into out_dir."""

    def _render(pdf_path: Path, out_dir: Path, dpi: int) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i in range(1, page_count + 1):
            p = out_dir / f"page-{i:04d}.png"
            p.write_bytes(b"\x89PNG")
            paths.append(p)
        return paths

    return _render


class _Spy:
    """Wraps a callable and counts invocations."""

    def __init__(self, fn):
        self._fn = fn
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self._fn(*args, **kwargs)


# --- hashing ---------------------------------------------------------------


def test_compute_file_hash_matches_sha256(tmp_path: Path) -> None:
    pdf = _write_pdf_bytes(tmp_path / "a.pdf", b"hello world")
    assert compute_file_hash(pdf) == hashlib.sha256(b"hello world").hexdigest()


# --- first ingest writes cache ---------------------------------------------


def test_ingest_writes_cache_and_returns_result(tmp_path: Path) -> None:
    pdf = _write_pdf_bytes(tmp_path / "doc.pdf")
    cache = tmp_path / "cache"

    result = ingest(
        pdf,
        cache_root=cache,
        convert=lambda _p: "# Chapter 1\n\nDense engineer notes.",
        render=_fake_render_factory(3),
    )

    assert isinstance(result, IngestionResult)
    assert result.from_cache is False
    assert result.page_count == 3
    assert result.is_scanned is False
    assert "Chapter 1" in result.markdown

    # Artifacts actually exist on disk, under the hash-keyed dir.
    assert result.markdown_path.is_file()
    assert result.markdown_path.parent == cache / result.file_hash
    assert len(result.page_image_paths) == 3
    assert all(p.is_file() for p in result.page_image_paths)
    assert (cache / result.file_hash / "manifest.json").is_file()


# --- cache hit: no re-ingestion --------------------------------------------


def test_second_ingest_hits_cache_without_rework(tmp_path: Path) -> None:
    pdf = _write_pdf_bytes(tmp_path / "doc.pdf")
    cache = tmp_path / "cache"
    convert = _Spy(lambda _p: "text body that is clearly present")
    render = _Spy(_fake_render_factory(2))

    first = ingest(pdf, cache_root=cache, convert=convert, render=render)
    second = ingest(pdf, cache_root=cache, convert=convert, render=render)

    assert convert.calls == 1  # not re-run on the cache hit
    assert render.calls == 1
    assert first.from_cache is False
    assert second.from_cache is True
    assert second.file_hash == first.file_hash
    assert second.markdown == first.markdown
    assert second.page_image_paths == first.page_image_paths


# --- cache invalidation ------------------------------------------------------


def test_cache_rebuilt_when_artifact_missing(tmp_path: Path) -> None:
    pdf = _write_pdf_bytes(tmp_path / "doc.pdf")
    cache = tmp_path / "cache"
    convert = _Spy(lambda _p: "present text body")
    render = _Spy(_fake_render_factory(2))

    first = ingest(pdf, cache_root=cache, convert=convert, render=render)
    first.page_image_paths[0].unlink()  # corrupt the cache

    second = ingest(pdf, cache_root=cache, convert=convert, render=render)

    assert convert.calls == 2  # rebuilt because an artifact was gone
    assert render.calls == 2
    assert second.from_cache is False
    assert all(p.is_file() for p in second.page_image_paths)


def test_force_rebuilds_even_with_valid_cache(tmp_path: Path) -> None:
    pdf = _write_pdf_bytes(tmp_path / "doc.pdf")
    cache = tmp_path / "cache"
    convert = _Spy(lambda _p: "present text body")
    render = _Spy(_fake_render_factory(1))

    ingest(pdf, cache_root=cache, convert=convert, render=render)
    forced = ingest(pdf, cache_root=cache, convert=convert, render=render, force=True)

    assert convert.calls == 2
    assert render.calls == 2
    assert forced.from_cache is False


# --- content-addressing ------------------------------------------------------


def test_different_content_uses_different_cache(tmp_path: Path) -> None:
    a = _write_pdf_bytes(tmp_path / "a.pdf", b"%PDF aaa")
    b = _write_pdf_bytes(tmp_path / "b.pdf", b"%PDF bbb")
    cache = tmp_path / "cache"

    ra = ingest(a, cache_root=cache, convert=lambda _p: "alpha text", render=_fake_render_factory(1))
    rb = ingest(b, cache_root=cache, convert=lambda _p: "beta text", render=_fake_render_factory(1))

    assert ra.file_hash != rb.file_hash
    assert ra.markdown_path.parent != rb.markdown_path.parent


# --- scanned detection -------------------------------------------------------


def test_scanned_pdf_flagged_when_no_text(tmp_path: Path) -> None:
    pdf = _write_pdf_bytes(tmp_path / "scan.pdf")
    cache = tmp_path / "cache"

    result = ingest(
        pdf,
        cache_root=cache,
        convert=lambda _p: "   \n  \n",  # image-only: no usable text layer
        render=_fake_render_factory(5),
    )

    assert result.is_scanned is True


# --- real end-to-end (markitdown + PyMuPDF) ---------------------------------


def test_ingest_real_pdf_end_to_end(tmp_path: Path) -> None:
    fitz = __import__("fitz")  # PyMuPDF; skip-free since it's a Phase-5 dep
    pdf = tmp_path / "real.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Chapter 1: Kinematics")
    doc.new_page().insert_text((72, 72), "Velocity is the rate of change of position.")
    doc.save(str(pdf))
    doc.close()

    cache = tmp_path / "cache"
    result = ingest(pdf, cache_root=cache, dpi=72)

    assert result.from_cache is False
    assert result.page_count == 2
    assert result.is_scanned is False
    assert "Kinematics" in result.markdown
    assert len(result.page_image_paths) == 2
    assert all(p.is_file() and p.stat().st_size > 0 for p in result.page_image_paths)

    # Second pass is a pure cache hit (no markitdown/PyMuPDF re-run needed).
    again = ingest(pdf, cache_root=cache, dpi=72)
    assert again.from_cache is True
    assert again.markdown == result.markdown
