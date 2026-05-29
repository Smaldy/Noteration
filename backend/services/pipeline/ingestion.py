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
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# Cache root: backend/cache/ (gitignored). One subdirectory per file hash.
CACHE_ROOT = Path(__file__).resolve().parents[2] / "cache"

MANIFEST_NAME = "manifest.json"
MARKDOWN_NAME = "document.md"
PAGES_DIRNAME = "pages"
MANIFEST_VERSION = 1
DEFAULT_DPI = 150

# A PDF with fewer than this many non-whitespace markdown chars *per page* has no
# usable text layer (scanned/image-only) and is flagged for the manual-structure
# fallback (docs/ai-pipeline.md stage 1) rather than fed to heading detection.
_MIN_CHARS_PER_PAGE = 8

# Converter: PDF path -> markdown text. Renderer: (PDF, out_dir, dpi) -> page
# image paths written under out_dir, page order ascending.
Converter = Callable[[Path], str]
Renderer = Callable[[Path, Path, int], "list[Path]"]


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


# --- default backends (imported lazily so unit tests stay dependency-free) ---


def _markitdown_convert(pdf_path: Path) -> str:
    from markitdown import MarkItDown

    return MarkItDown().convert(str(pdf_path)).text_content


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
    dpi: int = DEFAULT_DPI,
    force: bool = False,
) -> IngestionResult:
    """Convert + render a PDF, caching by content hash; reuse the cache if valid.

    ``force=True`` rebuilds even when a valid cache exists. The build runs in a
    staging directory that is swapped into place atomically, so a crash mid-ingest
    never leaves a partial cache that the cache-check would later trust.
    """
    pdf_path = Path(pdf_path)
    cache_root = Path(cache_root)
    file_hash = compute_file_hash(pdf_path)
    cache_dir = cache_root / file_hash

    if not force:
        cached = _load_cache(cache_dir, file_hash)
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

    return IngestionResult(
        file_hash=file_hash,
        markdown=markdown,
        markdown_path=cache_dir / MARKDOWN_NAME,
        page_image_paths=[cache_dir / PAGES_DIRNAME / name for name in manifest["page_files"]],
        page_count=page_count,
        is_scanned=is_scanned,
        from_cache=False,
    )


# --- internals --------------------------------------------------------------


def _looks_scanned(markdown: str, page_count: int) -> bool:
    if page_count <= 0:
        return True
    non_whitespace = sum(1 for ch in markdown if not ch.isspace())
    return non_whitespace < _MIN_CHARS_PER_PAGE * page_count


def _load_cache(cache_dir: Path, file_hash: str) -> IngestionResult | None:
    """Return a result from cache, or ``None`` if absent/stale/incomplete."""
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
    )


def _commit_cache(staging: Path, cache_dir: Path) -> None:
    """Move the freshly built staging dir into its final hash-keyed location.

    A rebuild (cache invalidated or ``force``) must overwrite any existing dir,
    so a stale/incomplete cache is cleared first. The queue is the single writer
    in this local app, so the brief window where the target is absent only ever
    looks like a cache miss to a concurrent reader (which then rebuilds).
    """
    cache_dir.parent.mkdir(parents=True, exist_ok=True)
    if cache_dir.exists():
        shutil.rmtree(cache_dir, ignore_errors=True)
    os.replace(staging, cache_dir)  # atomic on the same filesystem
