"""Schemas for the subjects API (Phase 9c).

Subjects are the top of the hierarchy and own the deadline ``exam_date``. The
upload flow needs to pick or create one before a PDF can be attached.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


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
    created_at: datetime
