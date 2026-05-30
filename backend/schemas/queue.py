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
    errors: list[QueueErrorTopicOut]


class RetryResult(BaseModel):
    topic_id: int
    retried_jobs: int  # 0 if the topic had no failed jobs
