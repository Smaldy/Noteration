"""Document service — upload→ingest and structure detection/confirmation.

Keeps the routers thin (logic lives here). The ingestion call is injectable so
the persistence + validation logic is testable without markitdown/PyMuPDF.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from backend.models import Document, Subject
from backend.models.enums import DocumentStatus
from backend.services.pipeline.ingestion import CACHE_ROOT, IngestionResult, ingest
from backend.services.pipeline.structure import ProposedStructure, detect_structure

# Original PDFs are kept (gitignored) so a forced re-ingest has the source again.
UPLOADS_DIR = CACHE_ROOT / "uploads"
PDF_MAGIC = b"%PDF"

IngestFn = Callable[[Path], IngestionResult]


class InvalidPDFError(ValueError):
    """Uploaded bytes are not a PDF."""


class SubjectNotFoundError(LookupError):
    """Referenced subject does not exist."""


class DocumentNotFoundError(LookupError):
    """Referenced document does not exist."""


class MarkdownUnavailableError(FileNotFoundError):
    """The document's cached markdown is missing (needs re-ingest)."""


def create_document(
    session: Session,
    *,
    subject_id: int,
    filename: str,
    data: bytes,
    ingest_fn: IngestFn = ingest,
    uploads_dir: str | Path = UPLOADS_DIR,
) -> tuple[Document, IngestionResult]:
    """Persist an uploaded PDF, ingest it (cached), and create a Document row."""
    if not data.startswith(PDF_MAGIC):
        raise InvalidPDFError("uploaded file is not a PDF")
    if session.get(Subject, subject_id) is None:
        raise SubjectNotFoundError(subject_id)

    pdf_path = _persist_upload(data, Path(uploads_dir))
    result = ingest_fn(pdf_path)

    document = Document(
        subject_id=subject_id,
        filename=filename,
        file_hash=result.file_hash,
        markdown_path=str(result.markdown_path),
        status=DocumentStatus.uploaded,
    )
    session.add(document)
    session.commit()
    return document, result


def detect_for_document(session: Session, document_id: int) -> ProposedStructure:
    """Re-run heading detection over a document's cached markdown."""
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(document_id)
    if not document.markdown_path:
        raise MarkdownUnavailableError(document_id)
    path = Path(document.markdown_path)
    if not path.is_file():
        raise MarkdownUnavailableError(str(path))
    return detect_structure(path.read_text(encoding="utf-8"))


def _persist_upload(data: bytes, uploads_dir: Path) -> Path:
    """Write the PDF under uploads/<hash>.pdf (idempotent, atomic)."""
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_hash = hashlib.sha256(data).hexdigest()
    pdf_path = uploads_dir / f"{file_hash}.pdf"
    if not pdf_path.exists():
        tmp = uploads_dir / f".{file_hash}.{os.getpid()}.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, pdf_path)
    return pdf_path
