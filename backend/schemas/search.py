"""Schema for the search API — a flat hit with a navigable breadcrumb."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from backend.models.enums import TopicPriority, TopicStatus


class SearchResultOut(BaseModel):
    """One match. ``kind`` discriminates topic vs chapter; ``status``/``priority``
    are populated for topics only. The breadcrumb fields let the client deep-link
    into the study view."""

    model_config = ConfigDict(from_attributes=True)

    kind: Literal["topic", "chapter"]
    id: int
    title: str
    subject_id: int
    subject_name: str
    document_id: int
    document_filename: str
    chapter_title: str
    status: TopicStatus | None = None
    priority: TopicPriority | None = None
