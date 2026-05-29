"""Document service — upload→ingest and structure detection/confirmation.

Keeps the routers thin (logic lives here). The ingestion call is injectable so
the persistence + validation logic is testable without markitdown/PyMuPDF.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import DocumentStatus, TopicPriority
from backend.schemas.structure import ChapterIn
from backend.services.pipeline.ingestion import CACHE_ROOT, IngestionResult, ingest
from backend.services.pipeline.structure import ProposedStructure, detect_structure
from backend.services.queue import QueueService

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


class AlreadyConfirmedError(Exception):
    """The document already has a confirmed structure (chapters exist)."""


class ConfirmCounts(NamedTuple):
    chapters_created: int
    topics_created: int
    topics_enqueued: int  # excludes 'skip' topics


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


def confirm_structure(
    session: Session,
    document_id: int,
    *,
    chapters: Sequence[ChapterIn],
    exam_date: date | None = None,
) -> ConfirmCounts:
    """Persist the reviewed tree and enqueue its non-skip topics.

    Chapters/topics are created first (so topics have ids), then each topic is
    enqueued via the queue (``skip`` topics create no jobs). Confirming sets the
    optional subject exam date (deadline mode) and moves the document to
    ``processing``. Re-confirming a document that already has chapters is refused.
    """
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(document_id)

    already = session.scalar(
        select(func.count())
        .select_from(Chapter)
        .where(Chapter.document_id == document_id)
    )
    if already:
        raise AlreadyConfirmedError(document_id)

    subject = session.get(Subject, document.subject_id)
    if exam_date is not None:
        subject.exam_date = exam_date

    created_topics: list[Topic] = []
    for ch_index, chapter_in in enumerate(chapters):
        chapter = Chapter(
            document_id=document.id,
            subject_id=document.subject_id,
            title=chapter_in.title,
            order_index=ch_index,
        )
        session.add(chapter)
        session.flush()  # assign chapter.id
        for t_index, topic_in in enumerate(chapter_in.topics):
            topic = Topic(
                chapter_id=chapter.id,
                title=topic_in.title,
                priority=topic_in.priority,
                order_index=t_index,
            )
            session.add(topic)
            created_topics.append(topic)
    session.flush()  # assign topic ids before enqueueing

    # Enqueue and flip status in the *same* transaction as the tree, so a crash
    # can't leave a confirmed-but-partially-queued document (re-confirm is
    # refused). 'skip' topics create no jobs.
    queue = QueueService(session)
    enqueued = 0
    for topic in created_topics:
        if topic.priority is TopicPriority.skip:
            continue
        queue.enqueue_topic(topic, commit=False)
        enqueued += 1

    document.status = DocumentStatus.processing
    session.commit()

    return ConfirmCounts(len(chapters), len(created_topics), enqueued)


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
