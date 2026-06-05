"""Schemas for the Library (home screen) document list (Phase 9)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from backend.models.enums import DocumentMode, DocumentStatus


class DocumentSummaryOut(BaseModel):
    """A document as shown in the Library list: metadata + topic-ready progress."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    subject_id: int
    subject_name: str
    subject_bookmarked: bool
    exam_date: date | None
    status: DocumentStatus
    status_detail: str | None
    source_type: str  # "pdf" | "audio"
    mode: DocumentMode
    uploaded_at: datetime
    topics_total: int
    topics_ready: int
    chapters_total: int
    chapters_running: int  # chapter lanes set to process (running)
