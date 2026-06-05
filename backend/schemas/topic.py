"""Schemas for the Study View reads (Phase 9d): document tree + topic content."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from backend.models.enums import (
    DocumentMode,
    DocumentStatus,
    FormulaState,
    TopicPriority,
    TopicStatus,
)

# --- document tree (sidebar) ------------------------------------------------


class TopicNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    priority: TopicPriority
    status: TopicStatus
    studied: bool
    bookmarked: bool
    order_index: int


class ChapterNodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    order_index: int
    topics: list[TopicNodeOut]


class DocumentTreeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: int
    subject_id: int
    status: DocumentStatus
    mode: DocumentMode
    chapters: list[ChapterNodeOut]


# --- topic content (Notes / Quiz / Flashcards tabs) -------------------------


class FormulaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    latex: str
    state: FormulaState
    confidence: float | None
    bbox: dict[str, Any] | None


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content_md: str
    is_manual: bool
    locked: bool
    stale: bool
    formulas: list[FormulaOut]


class MCQOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    question: str
    options: list[str]
    correct_index: int
    explanation: str
    is_manual: bool


class FlashcardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    front: str
    back: str
    is_manual: bool


class AttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str  # "image" | "audio"
    filename: str
    content_type: str
    # API path that serves the file (stamped in the service layer).
    url: str


class TopicContentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: TopicStatus
    studied: bool
    bookmarked: bool
    # The provider that generated this topic's AI content (the in-view provenance
    # stamp), from the notes-stage QueueJob; None for manual/ungenerated topics.
    generated_by: str | None = None
    notes: list[NoteOut]
    mcqs: list[MCQOut]
    flashcards: list[FlashcardOut]
    attachments: list[AttachmentOut] = []


class GenerateMoreRequest(BaseModel):
    """Ask for more of one assessment kind for a topic (on-demand)."""

    kind: Literal["mcqs", "flashcards"]
