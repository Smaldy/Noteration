"""Schemas for the floating to-do list widget."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TodoItemOut(BaseModel):
    """One to-do row: the pinned topic plus display labels and deep-link ids.

    ``studied`` is the topic's completed flag (the item's checkbox state) — the
    list stores only the reference, so it always mirrors the Notes-tab checkmark.
    """

    model_config = ConfigDict(from_attributes=True)

    topic_id: int
    title: str
    chapter_title: str
    document_id: int
    document_filename: str
    subject_id: int
    subject_name: str
    studied: bool
    created_at: datetime


class TodoAddRequest(BaseModel):
    """Pin topics to the to-do list (idempotent; duplicates are skipped)."""

    topic_ids: list[int] = Field(min_length=1)


class TodoClearedOut(BaseModel):
    """How many checked-off items a clear-completed removed."""

    removed: int
