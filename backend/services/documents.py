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
from backend.models.enums import (
    DocumentMode,
    DocumentStatus,
    QueueLaneState,
    TopicPriority,
    TopicStatus,
)
from backend.schemas.structure import ChapterIn
from backend.services.pipeline.ingestion import (
    UPLOADS_DIR,
    IngestionResult,
    OutlineEntry,
    ingest,
    read_toc,
)
from backend.services.pipeline.pdf_outline import (
    ChapterSlice,
    extract_chapters_from_toc,
    extract_pdf_structure,
)
from backend.services.pipeline.structure import (
    ProposedChapter,
    ProposedStructure,
    ProposedTopic,
    detect_structure,
)
from backend.services.queue import EXAM_STAGES, QueueService

PDF_MAGIC = b"%PDF"

IngestFn = Callable[[Path], IngestionResult]
PdfOutlineFn = Callable[[Path], ProposedStructure | None]
# Reads a PDF's embedded outline: (outline | None, total_pages). Injectable so the
# outline-primary detection path is unit-testable without a real TOC-bearing PDF.
OutlineReaderFn = Callable[[Path], "tuple[list[OutlineEntry] | None, int]"]


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
    mode: DocumentMode
    uploaded_at: datetime
    topics_total: int
    topics_ready: int


def list_documents(
    session: Session, *, mode: DocumentMode | None = None
) -> list[DocumentSummary]:
    """Documents (newest first) with subject info and topic-ready counts.

    ``mode`` scopes the list to one section: ``study`` for the Library, ``exam``
    for the Exam Prep section (``None`` returns all). A freshly uploaded document
    (structure not yet confirmed) has no topics and reports 0/0. Counts are
    computed in one grouped query, not per-document, to avoid an N+1.
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

    query = (
        select(Document, Subject.name, Subject.exam_date, Subject.bookmarked)
        .join(Subject, Document.subject_id == Subject.id)
        # Manual order first; newest-first as the tie-break for un-reordered rows.
        .order_by(
            Document.order_index.asc(),
            Document.uploaded_at.desc(),
            Document.id.desc(),
        )
    )
    if mode is not None:
        query = query.where(Document.mode == mode)
    rows = session.execute(query).all()

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
                mode=document.mode,
                uploaded_at=document.uploaded_at,
                topics_total=total,
                topics_ready=ready,
            )
        )
    return summaries


def reorder_documents(session: Session, ids: list[int]) -> None:
    """Set each listed document's ``order_index`` to its position in ``ids``.

    Unknown ids are ignored; documents not in the list keep their current index.
    """
    found = {
        doc.id: doc
        for doc in session.execute(
            select(Document).where(Document.id.in_(ids))
        ).scalars()
    }
    for position, doc_id in enumerate(ids):
        doc = found.get(doc_id)
        if doc is not None:
            doc.order_index = position
    session.commit()


def create_document(
    session: Session,
    *,
    subject_id: int,
    filename: str,
    data: bytes,
    mode: DocumentMode = DocumentMode.study,
    ingest_fn: IngestFn = ingest,
    uploads_dir: str | Path = UPLOADS_DIR,
) -> tuple[Document, IngestionResult]:
    """Persist an uploaded PDF, ingest it (cached), and create a Document row.

    ``mode`` records which section the upload belongs to: ``study`` (Library) runs
    the full notes+assessment pipeline; ``exam`` (Exam Prep) is assessment-only.
    """
    if not data.startswith(PDF_MAGIC):
        raise InvalidPDFError("uploaded file is not a PDF")
    if session.get(Subject, subject_id) is None:
        raise SubjectNotFoundError(subject_id)

    pdf_path = _persist_upload(data, Path(uploads_dir))
    result = ingest_fn(pdf_path)

    # New uploads sort to the front by default (smallest order_index), while
    # still respecting any manual order the user has set on existing cards.
    min_order = session.execute(select(func.min(Document.order_index))).scalar()
    document = Document(
        subject_id=subject_id,
        filename=filename,
        file_hash=result.file_hash,
        markdown_path=str(result.markdown_path),
        status=DocumentStatus.uploaded,
        mode=mode,
        order_index=(min_order if min_order is not None else 0) - 1,
    )
    session.add(document)
    session.commit()
    return document, result


def detect_for_document(
    session: Session,
    document_id: int,
    *,
    pdf_outline_fn: PdfOutlineFn = extract_pdf_structure,
    outline_reader: OutlineReaderFn = read_toc,
    uploads_dir: str | Path = UPLOADS_DIR,
) -> ProposedStructure:
    """Propose a chapter/topic tree for a document.

    Detection has three tiers, in order of preference:

    1. **Embedded outline (books).** When the original PDF carries a real TOC, its
       top-level entries become chapters *with page ranges* — the page ranges are
       what lazy per-chapter markdown needs to avoid running markitdown over the
       whole 700-page book (the context-explosion fix). Trash front/back matter is
       auto-skipped deterministically. This wins over markdown headings precisely
       because markdown headings carry no page mapping.
    2. **Markdown headings** over the cached markdown (slide decks/lecture PDFs that
       markitdown converts cleanly, books without an outline).
    3. **PDF outline/font-size fallback** (``extract_pdf_structure``) when the
       markdown yields nothing — ``docs/ai-pipeline.md`` Stage 2's no-model
       fallback so a plainly-structured document isn't reported as unrecognized.
    """
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(document_id)

    pdf_path = Path(uploads_dir) / f"{document.file_hash}.pdf"
    have_pdf = bool(document.file_hash) and pdf_path.is_file()

    # Tier 1: outline-backed book → chapters with page ranges. Gated to genuine
    # books: a slide deck exported with per-slide bookmarks ("Slide 1", "Slide 2")
    # also has a TOC, but each entry is a single page — slicing that gives N
    # one-page, all-auto-skipped "chapters". Those decks belong on the slide path
    # (Tier 3's extract_pdf_structure, which groups slides), so require real
    # multi-page chapter structure before taking Tier 1.
    if have_pdf:
        outline, total_pages = outline_reader(pdf_path)
        if outline is not None:
            slices = extract_chapters_from_toc(outline, total_pages)
            if _looks_like_book(slices):
                return _structure_from_slices(slices)

    # Tier 2: markdown headings.
    if not document.markdown_path:
        raise MarkdownUnavailableError(document_id)
    path = Path(document.markdown_path)
    if not path.is_file():
        raise MarkdownUnavailableError(str(path))

    proposed = detect_structure(path.read_text(encoding="utf-8"))
    if not proposed.needs_manual:
        return proposed

    # Tier 3: PDF outline/font-size fallback.
    if have_pdf:
        from_pdf = pdf_outline_fn(pdf_path)
        if from_pdf is not None and from_pdf.chapters:
            # The tree came from the PDF outline, not markdown headings, so the
            # notes stage can't slice the markdown per topic — flag it so review
            # warns that topic order matters (proportional slicing).
            from_pdf.has_headings = False
            return from_pdf
    return proposed


# A book's chapters span many pages; a bookmarked slide deck's "chapters" are one
# page each. Require at least this many genuinely multi-page chapters to treat the
# outline as a book (otherwise it's a deck → use the slide-grouping path).
_MIN_BOOK_CHAPTERS = 2


def _looks_like_book(slices: Sequence[ChapterSlice]) -> bool:
    """True when the outline has real multi-page chapter structure (not a deck)."""
    multipage = sum(1 for sl in slices if sl.page_end > sl.page_start)
    return multipage >= _MIN_BOOK_CHAPTERS


def _structure_from_slices(slices: Sequence[ChapterSlice]) -> ProposedStructure:
    """Build the proposed tree from outline chapter slices.

    Each slice is one chapter carrying its page range; its single topic (named for
    the chapter) seeds ``skip`` priority for trash/front-matter and ``medium``
    otherwise. ``has_headings`` stays ``True`` — each chapter is one page-bounded
    unit, so the proportional-slicing "topic order matters" warning doesn't apply
    (lazy per-chapter markdown scopes generation by page range, not topic order).
    """
    chapters = [
        ProposedChapter(
            title=sl.title,
            order_index=index,
            topics=[
                ProposedTopic(
                    title=sl.title,
                    order_index=0,
                    priority=TopicPriority.skip if sl.auto_skip else TopicPriority.medium,
                )
            ],
            page_start=sl.page_start,
            page_end=sl.page_end,
        )
        for index, sl in enumerate(slices)
    ]
    return ProposedStructure(
        chapters=chapters, needs_manual=False, method="pdf_outline", has_headings=True
    )


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

    created: list[tuple[Topic, Chapter]] = []
    for ch_index, chapter_in in enumerate(chapters):
        chapter = Chapter(
            document_id=document.id,
            subject_id=document.subject_id,
            title=chapter_in.title,
            order_index=ch_index,
            queue_state=chapter_in.queue_state,
            page_start=chapter_in.page_start,
            page_end=chapter_in.page_end,
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
            created.append((topic, chapter))
    session.flush()  # assign topic ids before enqueueing

    # Enqueue and flip status in the *same* transaction as the tree, so a crash
    # can't leave a confirmed-but-partially-queued document (re-confirm is
    # refused). A topic creates no jobs when it is 'skip' OR its chapter is
    # paused — a paused chapter's topics exist in the tree but stay un-enqueued
    # until the user resumes the chapter (the focus-only-what-you-study control).
    queue = QueueService(session)
    # Exam docs run the generation stage only (no formula stage — there's no Note
    # to attach equations to). Study docs use the default formula→generation order.
    stages = EXAM_STAGES if document.mode is DocumentMode.exam else None
    enqueued = 0
    for topic, chapter in created:
        if topic.priority is TopicPriority.skip:
            continue
        if chapter.queue_state is QueueLaneState.paused:
            continue
        if stages is None:
            queue.enqueue_topic(topic, commit=False)
        else:
            queue.enqueue_topic(topic, stages, commit=False)
        enqueued += 1

    document.status = DocumentStatus.processing
    session.commit()

    return ConfirmCounts(len(chapters), len(created), enqueued)


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
    subject_id: int
    status: DocumentStatus
    mode: DocumentMode
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
        document_id=document.id,
        subject_id=document.subject_id,
        status=document.status,
        mode=document.mode,
        chapters=chapter_nodes,
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
