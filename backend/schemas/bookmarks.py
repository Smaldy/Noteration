"""Schemas for bookmarks: the toggle body + the aggregated bookmarks view."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from backend.models.enums import TopicPriority, TopicStatus


class BookmarkUpdate(BaseModel):
    """Set a subject's or topic's bookmark flag (idempotent; not a toggle)."""

    bookmarked: bool


class BookmarkSubjectOut(BaseModel):
    """A bookmarked subject, with the primary document to deep-link into."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    accent_color: str | None
    exam_date: date | None
    bookmarked: bool
    created_at: datetime
    # ``None`` when the subject has no documents yet (chip non-navigable).
    document_id: int | None


class TopicBookmarkOut(BaseModel):
    """Minimal echo after toggling a topic bookmark."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    bookmarked: bool


class BookmarkTopicOut(BaseModel):
    """A bookmarked topic, with the breadcrumb needed to deep-link into study."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    subject_id: int
    subject_name: str
    document_id: int
    chapter_title: str
    status: TopicStatus
    priority: TopicPriority


class BookmarksOut(BaseModel):
    """Everything the Bookmarks view needs in one read."""

    subjects: list[BookmarkSubjectOut]
    topics: list[BookmarkTopicOut]
