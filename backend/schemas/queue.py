"""Schemas for the Queue / Processing API (Phase 9e)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QueueErrorTopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic_id: int
    title: str
    last_error: str | None


class QueueStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ready: int
    processing: int
    queued: int
    error: int
    total: int
    # Next provider-window wake-up (when work is deferred until a quota resets).
    resume_at: datetime | None
    # Why work is paused (the recorded provider error behind ``resume_at``).
    paused_reason: str | None
    # Per-document token-budget guard (cost defense-in-depth).
    token_spent: int
    token_budget: int
    budget_paused: bool
    errors: list[QueueErrorTopicOut]


class RetryResult(BaseModel):
    topic_id: int
    retried_jobs: int  # 0 if the topic had no failed jobs


# --- lane-aware status + history (Wave C) -----------------------------------


class LaneStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    subject_id: int
    subject_name: str
    state: str  # running / paused / overnight / waiting
    queue_state: str  # configured: running / paused / overnight
    ready: int
    processing: int
    queued: int
    error: int
    active_provider: str | None
    waiting_for: str | None
    resume_at: datetime | None


class ProviderLaneStateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    state: str  # active / cooling / disabled


class LaneQueueStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lanes: list[LaneStatusOut]
    active_provider: str | None
    providers: list[ProviderLaneStateOut]


class HistoryEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    subject_id: int | None
    subject_name: str | None
    topic_id: int | None
    topic_title: str | None
    provider_from: str | None
    provider_to: str | None
    detail: str | None
    created_at: datetime


class LaneStateUpdate(BaseModel):
    enabled: bool  # for the overnight toggle


class ClearHistoryResult(BaseModel):
    scope: str  # hour / day / all
    deleted: int  # how many history rows were removed
