"""Stage 1 — Ingestion: PDF → markdown + per-page image renders, disk-cached.

The first and cheapest cost lever (see docs/cost-strategy.md): ``markitdown``
strips visual noise so fewer input tokens ever reach a model, and PyMuPDF renders
each page once for later formula cropping. Both outputs are cached on disk keyed
by the file's content hash, so re-processing a document never re-pays ingestion.

This stage is pure with respect to the database: it produces cache artifacts and
returns an ``IngestionResult``. Attaching those to a ``Document`` row is the
caller's job (a later phase) — mirroring how the waterfall stays side-effect-free
and lets the queue own persistence.

The markdown converter and page renderer are *injected* (defaulting to
markitdown / PyMuPDF), so the orchestration + caching logic is unit-testable
without the heavy libraries, while one fixture-PDF test exercises the real ones.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Cache root: backend/cache/ (gitignored). One subdirectory per file hash.
CACHE_ROOT = Path(__file__).resolve().parents[2] / "cache"
# Original uploaded PDFs (content-addressed) live here so a later phase can
# re-derive page-range markdown without re-uploading. See documents.py.
UPLOADS_DIR = CACHE_ROOT / "uploads"

MANIFEST_NAME = "manifest.json"
MARKDOWN_NAME = "document.md"
PAGES_DIRNAME = "pages"
# Per-chapter lazy markdown cache: cache/<hash>/chapters/<chapter_idx>.md.
CHAPTERS_DIRNAME = "chapters"
MANIFEST_VERSION = 1
DEFAULT_DPI = 150

# A PDF with fewer than this many non-whitespace markdown chars *per page* has no
# usable text layer (scanned/image-only) and is flagged for the manual-structure
# fallback (docs/ai-pipeline.md stage 1) rather than fed to heading detection.
_MIN_CHARS_PER_PAGE = 8

# Fewer than this many embedded TOC entries isn't a real outline (a stray title
# bookmark or two); below it we treat the document as having no outline.
MIN_TOC_ENTRIES = 3

# One embedded table-of-contents entry: (level, title, 1-indexed page number).
OutlineEntry = tuple[int, str, int]

# Converter: PDF path -> markdown text. Renderer: (PDF, out_dir, dpi) -> page
# image paths written under out_dir, page order ascending. OutlineExtractor: PDF
# path -> its embedded TOC (or None when there's no usable outline).
Converter = Callable[[Path], str]
Renderer = Callable[[Path, Path, int], "list[Path]"]
OutlineExtractor = Callable[[Path], "list[OutlineEntry] | None"]


@dataclass(frozen=True)
class IngestionResult:
    """Outcome of ingesting one PDF; paths point at the on-disk cache."""

    file_hash: str
    markdown: str
    markdown_path: Path
    page_image_paths: list[Path]
    page_count: int
    is_scanned: bool  # no usable text layer → manual structure fallback
    from_cache: bool  # True when served from a prior ingestion (no re-pay)
    # Embedded TOC (level, title, 1-indexed page), or None when the PDF has no
    # usable outline. Drives chapter slicing + lazy per-chapter markdown for books;
    # always derived live from the source PDF (cheap) so it survives cache hits.
    outline: list[OutlineEntry] | None = None


# --- default backends (imported lazily so unit tests stay dependency-free) ---


def _markitdown_convert(pdf_path: Path) -> str:
    from markitdown import MarkItDown

    return MarkItDown().convert(str(pdf_path)).text_content


def read_toc(pdf_path: str | Path) -> tuple[list[OutlineEntry] | None, int]:
    """Return ``(outline, total_pages)`` for a PDF — the embedded-TOC primitive.

    The outline is the list of ``(level, title, 1-indexed page)`` entries, or
    ``None`` when the PDF has fewer than ``MIN_TOC_ENTRIES`` (no real outline).
    Never raises: a malformed/locked PDF or a missing PyMuPDF just yields
    ``(None, 0)`` so callers fall back to markdown/manual detection.
    """
    try:
        import fitz  # PyMuPDF, lazy
    except ImportError:  # pragma: no cover - PyMuPDF is a hard dep in practice
        return None, 0
    try:
        with fitz.open(str(pdf_path)) as doc:
            total_pages = doc.page_count
            toc = doc.get_toc(simple=True)  # [[level, title, page], ...]
    except Exception:  # noqa: BLE001 - any reader error → no outline, not a crash
        return None, 0
    if len(toc) < MIN_TOC_ENTRIES:
        return None, total_pages
    outline = [
        (max(1, int(level)), str(title), int(page)) for level, title, page, *_ in toc
    ]
    return outline, total_pages


def _default_outline(pdf_path: Path) -> list[OutlineEntry] | None:
    return read_toc(pdf_path)[0]


def _pymupdf_render(pdf_path: Path, out_dir: Path, dpi: int) -> list[Path]:
    import fitz  # PyMuPDF

    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with fitz.open(str(pdf_path)) as doc:
        width = max(4, len(str(doc.page_count)))
        for index, page in enumerate(doc, start=1):
            pixmap = page.get_pixmap(dpi=dpi)
            target = out_dir / f"page-{index:0{width}d}.png"
            pixmap.save(str(target))
            paths.append(target)
    return paths


# --- public API -------------------------------------------------------------


def compute_file_hash(pdf_path: Path, *, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of the file's bytes — the cache key. Streamed for large PDFs."""
    digest = hashlib.sha256()
    with open(pdf_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ingest(
    pdf_path: str | Path,
    *,
    cache_root: str | Path = CACHE_ROOT,
    convert: Converter = _markitdown_convert,
    render: Renderer = _pymupdf_render,
    extract_outline: OutlineExtractor = _default_outline,
    dpi: int = DEFAULT_DPI,
    force: bool = False,
) -> IngestionResult:
    """Convert + render a PDF, caching by content hash; reuse the cache if valid.

    ``force=True`` rebuilds even when a valid cache exists. The build runs in a
    staging directory that is swapped into place atomically, so a crash mid-ingest
    never leaves a partial cache that the cache-check would later trust.

    The embedded outline is read live from the source PDF on every call (cheap —
    just the TOC, no markitdown/rendering) and stamped onto the result, so a cache
    hit still carries it without bloating the cached artifacts.
    """
    pdf_path = Path(pdf_path)
    cache_root = Path(cache_root)
    file_hash = compute_file_hash(pdf_path)
    cache_dir = cache_root / file_hash
    outline = extract_outline(pdf_path)

    if not force:
        cached = _load_cache(cache_dir, file_hash, outline)
        if cached is not None:
            return cached

    # Cache miss (or forced rebuild). Convert first so a converter failure costs
    # nothing on disk; then build the rest in a private staging dir.
    markdown = convert(pdf_path)
    staging = cache_root / f".tmp-{file_hash}-{uuid.uuid4().hex}"
    try:
        page_paths = render(pdf_path, staging / PAGES_DIRNAME, dpi)
        page_count = len(page_paths)
        is_scanned = _looks_scanned(markdown, page_count)
        (staging / MARKDOWN_NAME).write_text(markdown, encoding="utf-8")
        manifest = {
            "version": MANIFEST_VERSION,
            "file_hash": file_hash,
            "source_filename": pdf_path.name,
            "page_count": page_count,
            "is_scanned": is_scanned,
            "markdown_file": MARKDOWN_NAME,
            "page_files": [p.name for p in page_paths],
        }
        (staging / MANIFEST_NAME).write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        _commit_cache(staging, cache_dir)
    finally:
        # Removes leftovers on failure; harmless no-op after a successful swap.
        shutil.rmtree(staging, ignore_errors=True)

    pages_dir = cache_dir / PAGES_DIRNAME
    return IngestionResult(
        file_hash=file_hash,
        markdown=markdown,
        markdown_path=cache_dir / MARKDOWN_NAME,
        page_image_paths=[pages_dir / name for name in manifest["page_files"]],
        page_count=page_count,
        is_scanned=is_scanned,
        from_cache=False,
        outline=outline,
    )


def get_chapter_markdown(
    pdf_path: str | Path,
    file_hash: str,
    chapter_idx: int,
    page_start: int,
    page_end: int,
    *,
    cache_root: str | Path = CACHE_ROOT,
    converter: Converter = _markitdown_convert,
) -> str:
    """Markdown for ONE chapter's page range (1-indexed inclusive), disk-cached.

    The fix for the 700-page context explosion: instead of converting the whole
    book at upload and re-sending the entire blob per topic, we convert only the
    chapter's pages, the first time that chapter is processed, and cache the result
    at ``cache/<hash>/chapters/<chapter_idx>.md``.

    On a cache hit the cached markdown is returned without touching the converter.
    On a miss the page range is extracted into a temporary sub-PDF (PyMuPDF
    ``insert_pdf``; ``page_start - 1`` because PyMuPDF is 0-indexed), converted, and
    the result cached atomically. ``converter`` is injectable so the slicing/cache
    logic is unit-testable without a real markitdown call.
    """
    cache_dir = Path(cache_root) / file_hash / CHAPTERS_DIRNAME
    cache_path = cache_dir / f"{chapter_idx}.md"
    if cache_path.is_file():
        return cache_path.read_text(encoding="utf-8")

    markdown = _convert_page_range(Path(pdf_path), page_start, page_end, converter)

    cache_dir.mkdir(parents=True, exist_ok=True)  # tolerate a concurrent create
    staging = cache_dir / f".{chapter_idx}-{uuid.uuid4().hex}.tmp"
    staging.write_text(markdown, encoding="utf-8")
    os.replace(staging, cache_path)  # atomic swap-in
    return markdown


def _convert_page_range(
    pdf_path: Path, page_start: int, page_end: int, converter: Converter
) -> str:
    """Extract a 1-indexed inclusive page range to a temp sub-PDF and convert it.

    The temp file is created closed and unlinked in a ``finally`` (not
    ``delete=True``) because on Windows a still-open NamedTemporaryFile can't be
    reopened by markitdown by path.
    """
    import fitz  # PyMuPDF, lazy

    tmp_path: Path | None = None
    with fitz.open(str(pdf_path)) as doc:
        last = doc.page_count - 1
        from_page = max(0, page_start - 1)
        to_page = min(page_end - 1, last)
        if to_page < from_page:
            to_page = from_page
        sub = fitz.open()
        try:
            sub.insert_pdf(doc, from_page=from_page, to_page=to_page)
            fd, name = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
            tmp_path = Path(name)
            sub.save(str(tmp_path))
        finally:
            sub.close()
    try:
        return converter(tmp_path)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


# --- internals --------------------------------------------------------------


def _looks_scanned(markdown: str, page_count: int) -> bool:
    if page_count <= 0:
        return True
    non_whitespace = sum(1 for ch in markdown if not ch.isspace())
    return non_whitespace < _MIN_CHARS_PER_PAGE * page_count


def _load_cache(
    cache_dir: Path, file_hash: str, outline: list[OutlineEntry] | None
) -> IngestionResult | None:
    """Return a result from cache, or ``None`` if absent/stale/incomplete.

    ``outline`` is supplied by the caller (read live from the source PDF) rather
    than cached, so it's stamped onto a cache-hit result too.
    """
    manifest_path = cache_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if manifest.get("version") != MANIFEST_VERSION:
        return None

    markdown_path = cache_dir / manifest["markdown_file"]
    page_paths = [cache_dir / PAGES_DIRNAME / name for name in manifest["page_files"]]
    # Trust the cache only if every referenced artifact is actually present.
    if not markdown_path.is_file() or not all(p.is_file() for p in page_paths):
        return None

    return IngestionResult(
        file_hash=file_hash,
        markdown=markdown_path.read_text(encoding="utf-8"),
        markdown_path=markdown_path,
        page_image_paths=page_paths,
        page_count=manifest["page_count"],
        is_scanned=manifest["is_scanned"],
        from_cache=True,
        outline=outline,
    )


def _commit_cache(staging: Path, cache_dir: Path) -> None:
    """Move the freshly built staging dir into its final hash-keyed location.

    A rebuild (cache invalidated or ``force``) must overwrite any existing dir.
    Rather than delete-then-recreate the same name — which races on Windows,
    where directory deletion can lag and the immediate recreate fails — the stale
    dir is moved aside first (a reliable atomic rename), the new one swapped in,
    and only then is the old one deleted. On failure the old dir is restored.
    """
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    if not cache_dir.exists():
        os.replace(staging, cache_dir)  # atomic on the same filesystem
        return

    backup = cache_dir.with_name(f"{cache_dir.name}.old-{uuid.uuid4().hex}")
    os.replace(cache_dir, backup)
    try:
        os.replace(staging, cache_dir)
    except OSError:
        os.replace(backup, cache_dir)  # restore the previous cache on failure
        raise
    shutil.rmtree(backup, ignore_errors=True)
