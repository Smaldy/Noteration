"""Schema for the aggregated (chapter/document/subject) assessment decks."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.schemas.topic import FlashcardOut, MCQOut


class AggregateAssessmentOut(BaseModel):
    """A pooled quiz + flashcard deck for one scope."""

    model_config = ConfigDict(from_attributes=True)

    scope: str  # "chapter" | "document" | "subject"
    id: int
    title: str
    topic_count: int
    mcqs: list[MCQOut]
    flashcards: list[FlashcardOut]
