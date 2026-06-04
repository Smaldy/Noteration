"""Pydantic schemas for the study (review / calendar) API."""

from __future__ import annotations

# Aliased: a model field is named ``date``, and a field named ``date`` with a
# default (ScheduleEntryUpdate) would shadow the bare ``date`` type when pydantic
# evaluates ``date | None``. Referencing the type as ``Date`` avoids the clash.
from datetime import date as Date
from datetime import time as Time
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

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
    due_date: Date | None


class ReviewRequest(BaseModel):
    grade: Grade


# "topic" → a topic study session (deep-links into the Study View); "subject" →
# a whole-subject session; "custom" → a free-text event; "deadline" → an exam/
# deadline marker (rendered red, drives the AI plan).
CalendarKind = Literal["topic", "subject", "custom", "deadline"]


class CalendarEntryOut(BaseModel):
    """A calendar item: an SM-2/deadline review, or a user/AI-authored session."""

    id: int
    date: Date
    start_time: str | None = None  # "HH:MM" wall-clock, or null for an all-day item
    source: ScheduleSource
    is_revision_buffer: bool
    is_deadline: bool = False
    kind: CalendarKind
    title: str  # effective display title (event name, else topic/subject name)
    description: str | None = None
    completed: bool = False
    completed_at: Date | None = None
    on_time: bool | None = None  # completed on/before its date; None if not done

    topic_id: int | None = None
    topic_title: str | None = None
    document_id: int | None = None  # for navigating into the Study View
    subject_id: int | None = None
    subject_name: str | None = None


class ScheduleEntryCreate(BaseModel):
    """Create a user calendar entry: topic, subject, custom event, or deadline."""

    date: Date
    start_time: Time | None = None  # accepts "HH:MM" / "HH:MM:SS"; null = all-day
    topic_id: int | None = None
    subject_id: int | None = None
    title: str | None = None
    description: str | None = None
    is_deadline: bool = False

    @model_validator(mode="after")
    def _at_least_one(self) -> "ScheduleEntryCreate":
        if self.is_deadline:
            if self.subject_id is None:
                raise ValueError("a deadline needs a subject_id")
            return self
        if self.topic_id is None and self.subject_id is None and not (
            self.title and self.title.strip()
        ):
            raise ValueError("provide a topic_id, subject_id, or a title")
        return self


class ScheduleEntryUpdate(BaseModel):
    """Partial update: any subset of date/start_time/title/description/completed.

    ``start_time`` is tri-state: omitted = leave unchanged; an explicit ``null`` =
    clear it (back to all-day); ``"HH:MM"`` = pin to that hour.
    """

    date: Date | None = None
    start_time: Time | None = None
    title: str | None = None
    description: str | None = None
    completed: bool | None = None


# Kept as the drag-drop reschedule body (date only); ScheduleEntryUpdate is a
# superset for the richer edit form.
class RescheduleRequest(BaseModel):
    date: Date


class PlanRequest(BaseModel):
    subject_id: int
    # The subject's topics the user marked already-studied (excluded from the
    # plan). None = leave each topic's studied flag as-is.
    studied_topic_ids: list[int] | None = None


class CatalogTopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    chapter_title: str
    document_id: int
    studied: bool


class CatalogSubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    topics: list[CatalogTopicOut]
