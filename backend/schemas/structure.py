"""Schemas for the upload + structure-review API (Phase 6)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import DocumentStatus, QueueLaneState, TopicPriority


class DocumentOut(BaseModel):
    """A document as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    filename: str
    file_hash: str
    status: DocumentStatus
    status_detail: str | None = None
    source_type: str = "pdf"


class UploadResult(BaseModel):
    """Result of uploading a document, before structure review.

    For a PDF, ``page_count``/``is_scanned``/``book_mode`` describe the ingest. For
    audio there is no ingest yet (it is transcribed in the background), so those
    stay at their defaults and ``document.status`` is ``transcribing``.
    """

    document: DocumentOut
    page_count: int = 0
    is_scanned: bool = False  # no text layer → the client should offer manual structure
    # True when this is a large outline-backed book whose whole-document markdown
    # was skipped (converted lazily per chapter). The upload UI frames it as a book.
    book_mode: bool = False


class TranscriptOut(BaseModel):
    """An audio document's transcript markdown (for the export button)."""

    document_id: int
    filename: str
    markdown: str


# --- proposed structure (detection output, read-only) -----------------------


class ProposedTopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    order_index: int
    # Default priority the review UI seeds (e.g. ``skip`` for trash chapters).
    priority: TopicPriority = TopicPriority.medium
    # 1-indexed PDF pages this topic's content lives on (slide-deck detection);
    # null for markdown/text trees. Round-trips through review → confirm so
    # generation can slice exactly these pages.
    pages: list[int] | None = None


class ProposedChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    order_index: int
    topics: list[ProposedTopicOut]
    # Outline-backed page range (1-indexed, inclusive); null for non-outline trees.
    page_start: int | None = None
    page_end: int | None = None


class ProposedStructureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chapters: list[ProposedChapterOut]
    needs_manual: bool
    method: str
    # False → markdown has no headings to slice by; notes are scoped per topic by
    # reading order, so the review UI warns the user that topic order matters.
    has_headings: bool = True


# --- confirmed structure (review submission, write) -------------------------


class TopicIn(BaseModel):
    """A topic as edited by the student in structure review."""

    title: str = Field(min_length=1)
    priority: TopicPriority = TopicPriority.medium
    # Passed through from the proposal (a review-time merge unions the lists);
    # user-added topics carry null and slice by heading/proportional order.
    pages: list[int] | None = None


class ChapterIn(BaseModel):
    title: str = Field(min_length=1)
    topics: list[TopicIn] = Field(min_length=1)
    # Per-chapter lane. Defaults to ``running``: confirming a document processes its
    # chapters (the expected "I confirmed it, so generate it" behaviour). A student
    # can still pause specific chapters in review (e.g. to skip parts of a long book
    # and not burn free-tier quota on chapters they aren't studying).
    queue_state: QueueLaneState = QueueLaneState.running
    # Outline-backed page range (1-indexed, inclusive); null for non-outline trees.
    page_start: int | None = None
    page_end: int | None = None


class ConfirmStructureIn(BaseModel):
    """The reviewed tree plus the optional exam date that drives the scheduler."""

    chapters: list[ChapterIn] = Field(min_length=1)
    exam_date: date | None = None  # sets the subject's exam_date (deadline mode)


# --- overnight batch upload -------------------------------------------------


class BatchItemResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    filename: str
    ok: bool
    document_id: int | None = None
    topics_enqueued: int = 0
    error: str | None = None


class BatchUploadResult(BaseModel):
    """Outcome of an overnight batch: per-file results plus rolled-up totals."""

    subject_id: int
    documents_ok: int
    topics_enqueued: int
    items: list[BatchItemResultOut]


class ConfirmStructureResult(BaseModel):
    document_id: int
    chapters_created: int
    topics_created: int
    topics_enqueued: int  # excludes 'skip' topics
