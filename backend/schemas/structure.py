"""Schemas for the upload + structure-review API (Phase 6)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

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


class ProposedChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    order_index: int
    topics: list[ProposedTopicOut]


class ProposedStructureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chapters: list[ProposedChapterOut]
    needs_manual: bool
    method: str


# --- confirmed structure (review submission, write) -------------------------


class TopicIn(BaseModel):
    """A topic as edited by the student in structure review."""

    title: str
    priority: TopicPriority = TopicPriority.medium


class ChapterIn(BaseModel):
    title: str
    topics: list[TopicIn]


class ConfirmStructureIn(BaseModel):
    """The reviewed tree plus the optional exam date that drives the scheduler."""

    chapters: list[ChapterIn]
    exam_date: str | None = None  # ISO date; sets the subject's exam_date


class ConfirmStructureResult(BaseModel):
    document_id: int
    chapters_created: int
    topics_created: int
    topics_enqueued: int  # excludes 'skip' topics
