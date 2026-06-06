"""Schemas for the subjects API (Phase 9c).

Subjects are the top of the hierarchy and own the deadline ``exam_date``. The
upload flow needs to pick or create one before a PDF can be attached.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import DocumentMode


class SubjectCreate(BaseModel):
    """Create a subject from the upload picker."""

    name: str = Field(min_length=1, max_length=200)
    accent_color: str | None = None
    exam_date: date | None = None


class SubjectOut(BaseModel):
    """A subject as returned to the client."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    accent_color: str | None
    exam_date: date | None
    bookmarked: bool
    created_at: datetime


# --- subject-wide topic tree (custom practice selector) ---------------------


class SelectableTopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    mcq_count: int
    flashcard_count: int


class SelectableChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    topics: list[SelectableTopicOut]


class SelectableDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    mode: DocumentMode
    chapters: list[SelectableChapterOut]


class SubjectTopicTreeOut(BaseModel):
    """Every selectable topic in a subject, grouped document→chapter."""

    model_config = ConfigDict(from_attributes=True)

    subject_id: int
    subject_name: str
    documents: list[SelectableDocumentOut]
