"""Document service — upload→ingest and structure detection/confirmation.

Keeps the routers thin (logic lives here). The ingestion call is injectable so
the persistence + validation logic is testable without markitdown/PyMuPDF.
"""

from __future__ import annotations

import hashlib
import logging
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
from backend.paths import CACHE_ROOT, UPLOADS_DIR
from backend.schemas.structure import ChapterIn, TopicIn
from backend.services.pipeline.ingestion import (
    IngestionResult,
    OutlineEntry,
    ingest,
    read_toc,
)
from backend.services.pipeline.pdf_outline import (
    ChapterSlice,
    extract_chapters_from_toc,
    extract_pdf_structure,
    is_trash,
)
from backend.services.pipeline.slide_grouping import (
    MIN_SLIDES_FOR_GROUPING,
    group_slides,
    load_cached_grouping,
    store_cached_grouping,
)
from backend.services.pipeline.structure import (
    ProposedChapter,
    ProposedStructure,
    ProposedTopic,
    SlideRun,
    detect_structure,
)
from backend.services.queue import EXAM_STAGES, QueueService

logger = logging.getLogger("backend.documents")

PDF_MAGIC = b"%PDF"

IngestFn = Callable[[Path], IngestionResult]
PdfOutlineFn = Callable[[Path], ProposedStructure | None]
# Reads a PDF's embedded outline: (outline | None, total_pages). Injectable so the
# outline-primary detection path is unit-testable without a real TOC-bearing PDF.
OutlineReaderFn = Callable[[Path], "tuple[list[OutlineEntry] | None, int]"]
# Groups a deck's (title, pages) slides into proposed chapters (model-backed);
# injectable so detection tests never build a real waterfall.
SlideGrouperFn = Callable[[list[SlideRun]], list[ProposedChapter]]


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
    status_detail: str | None
    source_type: str
    mode: DocumentMode
    uploaded_at: datetime
    topics_total: int
    topics_ready: int
    chapters_total: int
    chapters_running: int


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

    # Per-document chapter counts: total + how many lanes are set to process.
    chapter_rows = session.execute(
        select(
            Chapter.document_id,
            func.count(Chapter.id),
            func.coalesce(
                func.sum(
                    case((Chapter.queue_state == QueueLaneState.running, 1), else_=0)
                ),
                0,
            ),
        ).group_by(Chapter.document_id)
    ).all()
    chapter_counts = {
        doc_id: (total, running) for doc_id, total, running in chapter_rows
    }

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
        ch_total, ch_running = chapter_counts.get(document.id, (0, 0))
        summaries.append(
            DocumentSummary(
                id=document.id,
                filename=document.filename,
                subject_id=document.subject_id,
                subject_name=subject_name,
                subject_bookmarked=bookmarked,
                exam_date=exam_date,
                status=document.status,
                status_detail=document.status_detail,
                source_type=document.source_type,
                mode=document.mode,
                uploaded_at=document.uploaded_at,
                topics_total=total,
                topics_ready=ready,
                chapters_total=ch_total,
                chapters_running=ch_running,
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


def delete_document(session: Session, document_id: int) -> None:
    """Delete one document and everything under it (chapters → topics → …).

    The parent subject stays — with no documents left it shows as an empty
    subject card. Raises ``DocumentNotFoundError`` if it does not exist.
    """
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(document_id)
    session.delete(document)
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
        # Book-mode docs skip whole-doc markdown (lazy per chapter) → no path.
        markdown_path=str(result.markdown_path) if result.markdown_path else None,
        status=DocumentStatus.uploaded,
        mode=mode,
        order_index=(min_order if min_order is not None else 0) - 1,
    )
    session.add(document)
    session.commit()
    return document, result


class InvalidAudioError(ValueError):
    """Uploaded file is not an accepted audio format."""


def create_audio_document(
    session: Session,
    *,
    subject_id: int,
    filename: str,
    data: bytes,
    uploads_dir: str | Path = UPLOADS_DIR,
) -> Document:
    """Persist an uploaded audio file and create its (untranscribed) Document.

    The file is stored under ``uploads/<hash><ext>``; the Document starts in
    ``transcribing`` with ``source_type="audio"`` and no markdown yet — the
    transcription worker fills in the transcript and flips it to ``uploaded``,
    after which it follows the same structure-review → queue → notes flow as a PDF
    (minus the formula stage; there's no page to crop). Audio is always study mode.
    """
    from backend.services.transcription import SOURCE_TYPE_AUDIO, is_audio_filename

    if not is_audio_filename(filename):
        raise InvalidAudioError(filename)
    if not data:
        raise InvalidAudioError("empty audio file")
    if session.get(Subject, subject_id) is None:
        raise SubjectNotFoundError(subject_id)

    file_hash = _persist_audio(data, filename, Path(uploads_dir))
    min_order = session.execute(select(func.min(Document.order_index))).scalar()
    document = Document(
        subject_id=subject_id,
        filename=filename,
        file_hash=file_hash,
        markdown_path=None,
        source_type=SOURCE_TYPE_AUDIO,
        status=DocumentStatus.transcribing,
        mode=DocumentMode.study,
        order_index=(min_order if min_order is not None else 0) - 1,
    )
    session.add(document)
    session.commit()
    return document


def retrigger_transcription(session: Session, document_id: int) -> Document:
    """Flip a failed/errored audio document back to ``transcribing`` to retry."""
    document = session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError(document_id)
    from backend.services.transcription import SOURCE_TYPE_AUDIO

    if document.source_type != SOURCE_TYPE_AUDIO:
        raise DocumentNotFoundError(document_id)
    document.status = DocumentStatus.transcribing
    document.status_detail = None
    session.commit()
    return document


def detect_for_document(
    session: Session,
    document_id: int,
    *,
    pdf_outline_fn: PdfOutlineFn = extract_pdf_structure,
    outline_reader: OutlineReaderFn = read_toc,
    uploads_dir: str | Path = UPLOADS_DIR,
    slide_grouper: SlideGrouperFn | None = None,
    cache_root: str | Path = CACHE_ROOT,
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
       markdown yields nothing — ``docs/architecture.md`` Stage 2's no-model
       fallback so a plainly-structured document isn't reported as unrecognized.
       When this tier recognizes a slide deck, ONE small model call (titles only,
       disk-cached by file hash, silently skipped when no provider has headroom)
       groups the slides into real topics/chapters so a deck doesn't fragment
       into near-duplicate one-slide topics; the heuristic tree is the fallback.

    ``slide_grouper`` overrides the model-backed grouping call (tests); ``None``
    builds the provider waterfall from Settings on demand.
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

    # Tier 3: PDF outline/font-size fallback. A cached grouping is self-contained
    # (titles + pages), so probe it first and skip the whole-document heading
    # scan — re-opening the review screen costs one small file read.
    if have_pdf:
        cached = load_cached_grouping(cache_root, document.file_hash)
        if cached:
            return _grouped_structure(cached)
        from_pdf = pdf_outline_fn(pdf_path)
        if from_pdf is not None and from_pdf.chapters:
            grouped = _grouped_slide_structure(
                session,
                document,
                from_pdf,
                slide_grouper=slide_grouper,
                cache_root=cache_root,
            )
            if grouped is not None:
                return grouped
            # The tree came from the PDF outline, not markdown headings, so the
            # notes stage can't slice the markdown per topic — flag it so review
            # warns that topic order matters (proportional slicing).
            from_pdf.has_headings = False
            return from_pdf
    return proposed


def _grouped_slide_structure(
    session: Session,
    document: Document,
    proposed: ProposedStructure,
    *,
    slide_grouper: SlideGrouperFn | None,
    cache_root: str | Path,
) -> ProposedStructure | None:
    """The AI-grouped tree for a slide deck, or ``None`` to keep the heuristic.

    Small decks aren't worth a call. A success is cached by file hash (like
    ingestion) — ``detect_for_document`` probes that cache before this runs, so
    the call is paid at most once per document. Any failure — provider
    exhaustion, unusable output — quietly falls back to the heuristic tree:
    grouping is an upgrade, never a gate.
    """
    slides = proposed.slides
    if not slides or len(slides) < MIN_SLIDES_FOR_GROUPING:
        return None

    try:
        if slide_grouper is not None:
            chapters = slide_grouper(slides)
        else:
            from backend.services.providers.factory import (
                build_waterfall_from_settings,
            )
            from backend.services.settings import get_settings

            waterfall = build_waterfall_from_settings(get_settings(session))
            chapters = group_slides(waterfall, slides)
    except Exception:  # noqa: BLE001 - best-effort; the heuristic tree still works
        logger.warning(
            "slide grouping failed for document %s; using heuristic tree",
            document.id,
            exc_info=True,
        )
        return None
    if not chapters:
        return None

    store_cached_grouping(cache_root, document.file_hash, chapters)
    return _grouped_structure(chapters)


def _grouped_structure(chapters: list[ProposedChapter]) -> ProposedStructure:
    """Wrap grouped chapters: every topic carries pages, so slicing is exact.

    ``has_headings`` stays True — the "topic order matters" review warning exists
    for whole-document proportional slicing, which never runs here: detected
    topics carry their exact pages, and even a topic the user *adds* during
    review (no pages) stays scoped to its chapter's page range, because grouped
    chapters carry ``page_start``/``page_end`` (see generation.load_topic_source).
    """
    return ProposedStructure(
        chapters=chapters, needs_manual=False, method="ai_grouping", has_headings=True
    )


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
    the chapter) seeds ``medium`` priority. ``has_headings`` stays ``True`` — each
    chapter is one page-bounded unit, so the proportional-slicing "topic order
    matters" warning doesn't apply (lazy per-chapter markdown scopes generation by
    page range, not topic order).

    Trash front/back matter (cover, copyright, dedication, index, …) is **dropped
    entirely** rather than proposed as a skip topic: the user never wants notes for
    it, and leaving it in only clutters the topic list / queue (user-reported). The
    page span the book uses for trash pages is simply not covered — that's fine,
    nothing reads it. ``_looks_like_book`` still sees the full slices, so dropping a
    multi-page back-matter entry can't flip a real book onto the slide path.
    """
    kept = [sl for sl in slices if not is_trash(sl.title)]
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
        for index, sl in enumerate(kept)
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
                pdf_pages=sorted(set(topic_in.pages)) if topic_in.pages else None,
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
    # The generation-only stage set (no formula) is used when there's no PDF page to
    # crop equations from: exam docs (no notes) and audio docs (transcript only).
    # Study PDFs use the default formula→generation order.
    no_formula = (
        document.mode is DocumentMode.exam
        or document.source_type == "audio"
    )
    stages = EXAM_STAGES if no_formula else None
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
    raw_topic_count: dict[int, int] = {}
    for topic in topics:
        raw_topic_count[topic.chapter_id] = raw_topic_count.get(topic.chapter_id, 0) + 1
        # Drop front/back-matter topics (copyright, dedication, …) so they never
        # clutter the sidebar. New uploads never create these (filtered at
        # detection); this also cleans books confirmed before that fix landed.
        if is_trash(topic.title):
            continue
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

    def _keep(chapter: Chapter) -> bool:
        if is_trash(chapter.title):
            return False  # a whole front/back-matter chapter (e.g. "Index")
        # A chapter that *had* topics but lost them all to the trash filter is now
        # an empty heading — drop it. A genuinely empty chapter (never had topics)
        # is preserved, as before.
        had = raw_topic_count.get(chapter.id, 0)
        return not (had and not by_chapter.get(chapter.id))

    chapter_nodes = [
        ChapterNode(
            id=chapter.id,
            title=chapter.title,
            order_index=chapter.order_index,
            topics=by_chapter.get(chapter.id, []),
        )
        for chapter in chapters
        if _keep(chapter)
    ]
    return DocumentTree(
        document_id=document.id,
        subject_id=document.subject_id,
        status=document.status,
        mode=document.mode,
        chapters=chapter_nodes,
    )


@dataclass
class ChapterStatus:
    """One chapter's lane state + per-status topic counts for the Queue page."""

    id: int
    title: str
    page_start: int | None
    page_end: int | None
    queue_state: QueueLaneState
    order_index: int
    topics_total: int
    topics_ready: int
    topics_processing: int
    topics_queued: int
    topics_error: int


def get_chapter_statuses(session: Session, document_id: int) -> list[ChapterStatus]:
    """Per-chapter lane state + topic-status counts for a document (one query).

    Counts are computed in a single grouped query joining Chapter→Topic (no N+1).
    Chapters with no topics still appear (outer join). Ordered by reading order.
    """
    if session.get(Document, document_id) is None:
        raise DocumentNotFoundError(document_id)

    def _count(status: TopicStatus):
        return func.coalesce(
            func.sum(case((Topic.status == status, 1), else_=0)), 0
        )

    rows = session.execute(
        select(
            Chapter.id,
            Chapter.title,
            Chapter.page_start,
            Chapter.page_end,
            Chapter.queue_state,
            Chapter.order_index,
            func.count(Topic.id),
            _count(TopicStatus.ready),
            _count(TopicStatus.processing),
            _count(TopicStatus.queued),
            _count(TopicStatus.error),
        )
        .select_from(Chapter)
        .outerjoin(Topic, Topic.chapter_id == Chapter.id)
        .where(Chapter.document_id == document_id)
        .group_by(Chapter.id)
        .order_by(Chapter.order_index, Chapter.id)
    ).all()

    return [
        ChapterStatus(
            id=row[0],
            title=row[1],
            page_start=row[2],
            page_end=row[3],
            queue_state=row[4],
            order_index=row[5],
            topics_total=row[6],
            topics_ready=row[7],
            topics_processing=row[8],
            topics_queued=row[9],
            topics_error=row[10],
        )
        for row in rows
        # Front/back matter is never processed — keep it out of the queue view.
        if not is_trash(row[1])
    ]


@dataclass
class DocumentChapters:
    """One book's chapter lanes, for the Queue page's always-visible accordion."""

    document_id: int
    filename: str
    subject_id: int
    subject_name: str
    chapters: list[ChapterStatus]


def get_book_chapter_groups(session: Session) -> list[DocumentChapters]:
    """Per-document chapter lanes for every multi-chapter (book) document.

    The Queue page used to show chapter resume/pause controls only when it carried
    a ``?document_id=`` query param, which only the post-confirm redirect set — so
    navigating back to the queue any other way "collapsed" a book into its bare
    subject lane and the user lost the per-chapter controls (user-reported). This
    returns the chapter lanes for *all* books in one query, so the queue can always
    show them without a param.

    Returns the chapters for **every active document**, regardless of chapter count,
    so the Queue page can nest them under their subject lane card (expandable) and
    offer per-chapter pause/resume — including single-chapter slide decks, whose
    chapter is otherwise unreachable (the subject lane resumes the *subject*, not the
    chapter). A document whose every chapter is running *and* fully ready is finished
    and dropped (it belongs in the Library, not the active queue). Trash
    front/back-matter chapters are filtered exactly as ``get_chapter_statuses`` does.
    """
    groups: dict[int, DocumentChapters] = {}
    candidate_ids = set(
        session.execute(select(Chapter.document_id).distinct()).scalars().all()
    )
    for doc_id in candidate_ids:
        chapters = get_chapter_statuses(session, doc_id)
        if not chapters:
            continue
        finished = all(
            ch.queue_state is QueueLaneState.running
            and ch.topics_ready >= ch.topics_total
            for ch in chapters
        )
        if finished:
            continue
        document = session.get(Document, doc_id)
        if document is None:  # pragma: no cover - referential integrity
            continue
        subject = session.get(Subject, document.subject_id)
        groups[doc_id] = DocumentChapters(
            document_id=doc_id,
            filename=document.filename,
            subject_id=document.subject_id,
            subject_name=subject.name if subject else "",
            chapters=chapters,
        )

    # Order by the Library's manual order so the queue matches the user's layout.
    order = {
        doc.id: (doc.order_index, doc.id)
        for doc in session.execute(
            select(Document).where(Document.id.in_(groups))
        ).scalars()
    }
    return sorted(groups.values(), key=lambda g: order.get(g.document_id, (0, 0)))


@dataclass
class BatchItemResult:
    """One file's outcome in an overnight batch."""

    filename: str
    ok: bool
    document_id: int | None = None
    topics_enqueued: int = 0
    error: str | None = None


@dataclass
class BatchResult:
    subject_id: int
    items: list[BatchItemResult]

    @property
    def documents_ok(self) -> int:
        return sum(1 for i in self.items if i.ok)

    @property
    def topics_enqueued(self) -> int:
        return sum(i.topics_enqueued for i in self.items)


def _proposed_to_chapters(structure: ProposedStructure, fallback_title: str) -> list[ChapterIn]:
    """Turn a detected structure into a confirmable tree for unattended batch.

    No human reviews this, so it must always yield at least one chapter with
    one topic: an empty/headingless detection collapses to a single topic
    covering the whole document (generation then slices it by reading order),
    which is exactly what a lone confirmed topic does today.
    """
    chapters: list[ChapterIn] = []
    for chapter in structure.chapters:
        topics = [
            TopicIn(title=topic.title, priority=topic.priority, pages=topic.pages)
            for topic in chapter.topics
        ]
        if not topics:
            continue
        chapters.append(
            ChapterIn(
                title=chapter.title,
                topics=topics,
                page_start=chapter.page_start,
                page_end=chapter.page_end,
            )
        )
    if not chapters:
        chapters.append(
            ChapterIn(title=fallback_title, topics=[TopicIn(title=fallback_title)])
        )
    return chapters


def batch_process_overnight(
    session: Session,
    *,
    subject_id: int,
    files: Sequence[tuple[str, bytes]],
    uploads_dir: str | Path = UPLOADS_DIR,
    ingest_fn: IngestFn = ingest,
) -> BatchResult:
    """Ingest, auto-detect, and auto-confirm many PDFs for overnight generation.

    The unattended counterpart to the upload → review → confirm flow: each PDF
    runs create → detect → confirm with no manual step, then the whole subject
    lane is switched to ``overnight`` so the worker drains it in the background
    (and, when ``overnight_use_gemini`` is set, through Gemini). One bad file is
    recorded and skipped — it never aborts the rest of the batch, which is the
    point of dropping 20 PDFs and walking away.
    """
    if session.get(Subject, subject_id) is None:
        raise SubjectNotFoundError(subject_id)

    items: list[BatchItemResult] = []
    for filename, data in files:
        try:
            document, _ = create_document(
                session,
                subject_id=subject_id,
                filename=filename,
                data=data,
                uploads_dir=uploads_dir,
                ingest_fn=ingest_fn,
            )
            structure = detect_for_document(
                session, document.id, uploads_dir=uploads_dir
            )
            chapters = _proposed_to_chapters(structure, Path(filename).stem or filename)
            counts = confirm_structure(session, document.id, chapters=chapters)
            items.append(
                BatchItemResult(
                    filename=filename,
                    ok=True,
                    document_id=document.id,
                    topics_enqueued=counts.topics_enqueued,
                )
            )
        except InvalidPDFError:
            items.append(BatchItemResult(filename, ok=False, error="not_a_pdf"))
        except Exception as exc:  # noqa: BLE001 - one bad PDF must not sink the batch
            logger.exception("Batch overnight: %s failed", filename)
            session.rollback()
            items.append(BatchItemResult(filename, ok=False, error=str(exc)[:200]))

    # Switch the whole lane to overnight so its jobs drain in the background and
    # take the overnight provider route (quality model, or Gemini when opted in).
    if any(item.ok for item in items):
        QueueService(session).set_overnight(subject_id, True)

    return BatchResult(subject_id=subject_id, items=items)


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


def _persist_audio(data: bytes, filename: str, uploads_dir: Path) -> str:
    """Write audio under uploads/<hash><ext> (idempotent, atomic); return hash."""
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_hash = hashlib.sha256(data).hexdigest()
    ext = Path(filename).suffix.lower()
    audio_path = uploads_dir / f"{file_hash}{ext}"
    if not audio_path.exists():
        tmp = uploads_dir / f".{file_hash}.{os.getpid()}.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, audio_path)
    return file_hash
