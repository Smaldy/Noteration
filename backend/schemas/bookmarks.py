"""Schemas for bookmarks: the toggle body + the aggregated bookmarks view."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from backend.models.enums import TopicPriority, TopicStatus
from backend.schemas.subject import SubjectOut


class BookmarkUpdate(BaseModel):
    """Set a subject's or topic's bookmark flag (idempotent; not a toggle)."""

    bookmarked: bool


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

    subjects: list[SubjectOut]
    topics: list[BookmarkTopicOut]
