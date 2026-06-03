"""Schemas for editing notes (manual edits + manual note blocks)."""

from __future__ import annotations

from pydantic import BaseModel


class NoteUpdate(BaseModel):
    """Partial update of a note. Only provided fields change.

    ``content_md`` is the edited markdown (what the TipTap editor serializes back);
    ``locked`` toggles the per-note lock that protects it from regeneration.
    """

    content_md: str | None = None
    locked: bool | None = None


class NoteCreate(BaseModel):
    """Add a manual note block under a topic (below the AI note)."""

    topic_id: int
    content_md: str = ""
