"""Schemas for the subject/topic bookmark toggles."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BookmarkUpdate(BaseModel):
    """Set a subject's or topic's bookmark flag (idempotent; not a toggle)."""

    bookmarked: bool


class TopicBookmarkOut(BaseModel):
    """Minimal echo after toggling a topic bookmark."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    bookmarked: bool
