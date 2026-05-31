"""Document service — upload→ingest and structure detection/confirmation.

Keeps the routers thin (logic lives here). The ingestion call is injectable so
the persistence + validation logic is testable without markitdown/PyMuPDF.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.models.enums import DocumentStatus, TopicPriority, TopicStatus
from backend.schemas.structure import ChapterIn
from backend.services.pipeline.ingestion import CACHE_ROOT, IngestionResult, ingest
from backend.services.pipeline.pdf_outline import extract_pdf_structure
from backend.services.pipeline.structure import ProposedStructure, detect_structure
from backend.services.queue import QueueService

# Original PDFs are kept (gitignored) so a forced re-ingest has the source again.
UPLOADS_DIR = CACHE_ROOT / "uploads"
PDF_MAGIC = b"%PDF"

IngestFn = Callable[[Path], IngestionResult]
PdfOutlineFn = Callable[[Path], ProposedStructure | None]


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


@dataclass
class DocumentSummary:
    """One Library row: a document plus its subject and topic-ready progress."""

    id: int
    filename: str
    subject_id: int
    subject_name: str
    subject_bookmarked: bool
    exam_date: date | None
    status: DocumentStatus
    uploaded_at: datetime
    topics_total: int
    topics_ready: int


def list_documents(session: Session) -> list[DocumentSummary]:
    """All documents (newest first) with subject info and topic-ready counts.

    A freshly uploaded document (structure not yet confirmed) has no topics and
    reports 0/0. Counts are computed in one grouped query, not per-document, to
    avoid an N+1 over the library.
    """
    count_rows = session.execute(
        select(
            Chapter.document_id,
            func.count(Topic.id),
            func.sum(case((Topic.status == TopicStatus.ready, 1), else_=0)),
        )
        .join(Topic, Topic.chapter_id == Chapter.id)
        .group_by(Chapter.document_id)
    ).all()
    counts = {doc_id: (total, ready or 0) for doc_id, total, ready in count_rows}

    rows = session.execute(
        select(Document, Subject.name, Subject.exam_date, Subject.bookmarked)
        .join(Subject, Document.subject_id == Subject.id)
        .order_by(Document.uploaded_at.desc(), Document.id.desc())
    ).all()

    summaries: list[DocumentSummary] = []
    for document, subject_name, exam_date, bookmarked in rows:
        total, ready = counts.get(document.id, (0, 0))
        summaries.append(
            DocumentSummary(
                id=document.id,
                filename=document.filename,
                subject_id=document.subject_id,
                subject_name=subject_name,
                subject_bookmarked=bookmarked,
                exam_date=exam_date,
                status=document.status,
                uploaded_at=document.uploaded_at,
                topics_total=total,
                topics_ready=ready,
            )
        )
    return summaries


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


def detect_for_document(
    session: Session,
    document_id: int,
    *,
    pdf_outline_fn: PdfOutlineFn = extract_pdf_structure,
    uploads_dir: str | Path = UPLOADS_DIR,
) -> ProposedStructure:
    """Propose a chapter/topic tree for a document.

    Heading detection over the cached markdown is the primary signal. When that
    finds nothing (``needs_manual`` — markitdown often emits no headings for slide
    decks/lecture PDFs), fall back to mining the original PDF's embedded outline
    and font sizes (``docs/ai-pipeline.md`` Stage 2's sanctioned no-model
    fallback) so a plainly-structured document isn't reported as unrecognized.
    """
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(document_id)
    if not document.markdown_path:
        raise MarkdownUnavailableError(document_id)
    path = Path(document.markdown_path)
    if not path.is_file():
        raise MarkdownUnavailableError(str(path))

    proposed = detect_structure(path.read_text(encoding="utf-8"))
    if not proposed.needs_manual:
        return proposed

    pdf_path = Path(uploads_dir) / f"{document.file_hash}.pdf"
    if document.file_hash and pdf_path.is_file():
        from_pdf = pdf_outline_fn(pdf_path)
        if from_pdf is not None and from_pdf.chapters:
            return from_pdf
    return proposed


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


@dataclass
class TopicNode:
    id: int
    title: str
    priority: TopicPriority
    status: TopicStatus
    studied: bool
    bookmarked: bool
    order_index: int


@dataclass
class ChapterNode:
    id: int
    title: str
    order_index: int
    topics: list[TopicNode]


@dataclass
class DocumentTree:
    document_id: int
    status: DocumentStatus
    chapters: list[ChapterNode]


def get_document_tree(session: Session, document_id: int) -> DocumentTree:
    """The confirmed chapter/topic tree for the Study View sidebar.

    Chapters and topics come back ordered (order_index, id); topics are grouped
    into chapters in one pass, so no N+1 over the tree.
    """
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(document_id)

    chapters = (
        session.execute(
            select(Chapter)
            .where(Chapter.document_id == document_id)
            .order_by(Chapter.order_index, Chapter.id)
        )
        .scalars()
        .all()
    )
    topics = (
        session.execute(
            select(Topic)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(Chapter.document_id == document_id)
            .order_by(Topic.order_index, Topic.id)
        )
        .scalars()
        .all()
    )

    by_chapter: dict[int, list[TopicNode]] = {}
    for topic in topics:
        by_chapter.setdefault(topic.chapter_id, []).append(
            TopicNode(
                id=topic.id,
                title=topic.title,
                priority=topic.priority,
                status=topic.status,
                studied=topic.studied,
                bookmarked=topic.bookmarked,
                order_index=topic.order_index,
            )
        )

    chapter_nodes = [
        ChapterNode(
            id=chapter.id,
            title=chapter.title,
            order_index=chapter.order_index,
            topics=by_chapter.get(chapter.id, []),
        )
        for chapter in chapters
    ]
    return DocumentTree(
        document_id=document.id, status=document.status, chapters=chapter_nodes
    )


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
