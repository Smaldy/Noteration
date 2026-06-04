"""Schemas for the upload + structure-review API (Phase 6)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import DocumentStatus, TopicPriority


class DocumentOut(BaseModel):
    """A document as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_id: int
    filename: str
    file_hash: str
    status: DocumentStatus


class UploadResult(BaseModel):
    """Result of uploading + ingesting a PDF, before structure review."""

    document: DocumentOut
    page_count: int
    is_scanned: bool  # no text layer → the client should offer manual structure


# --- proposed structure (detection output, read-only) -----------------------


class ProposedTopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    order_index: int
    # Default priority the review UI seeds (e.g. ``skip`` for trash chapters).
    priority: TopicPriority = TopicPriority.medium


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


class ChapterIn(BaseModel):
    title: str = Field(min_length=1)
    topics: list[TopicIn] = Field(min_length=1)


class ConfirmStructureIn(BaseModel):
    """The reviewed tree plus the optional exam date that drives the scheduler."""

    chapters: list[ChapterIn] = Field(min_length=1)
    exam_date: date | None = None  # sets the subject's exam_date (deadline mode)


class ConfirmStructureResult(BaseModel):
    document_id: int
    chapters_created: int
    topics_created: int
    topics_enqueued: int  # excludes 'skip' topics
