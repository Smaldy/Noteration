"""Schemas for the chapter-lane API (Chapter Lanes)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.models.enums import QueueLaneState


class ChapterQueueStateUpdate(BaseModel):
    """Set a chapter lane to running / paused / overnight."""

    queue_state: QueueLaneState


class ChapterStatusOut(BaseModel):
    """A chapter's lane state + per-status topic counts (Queue page)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    page_start: int | None
    page_end: int | None
    queue_state: QueueLaneState
    topics_total: int
    topics_ready: int
    topics_processing: int
    topics_queued: int
    topics_error: int


class DocumentChaptersOut(BaseModel):
    """One book's chapter lanes, grouped under its document (Queue page)."""

    model_config = ConfigDict(from_attributes=True)

    document_id: int
    filename: str
    subject_id: int
    subject_name: str
    chapters: list[ChapterStatusOut]
