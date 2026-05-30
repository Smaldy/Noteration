"""Pydantic schemas for the study (review / calendar) API."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from backend.models.enums import ScheduleSource
from backend.services.scheduler import Grade


class FlashcardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int
    front: str
    back: str
    ease_factor: float
    interval: int
    repetitions: int
    due_date: date | None


class ReviewRequest(BaseModel):
    grade: Grade


class CalendarEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    topic_id: int
    date: date
    is_revision_buffer: bool
    source: ScheduleSource
