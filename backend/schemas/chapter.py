"""Schemas for the chapter-lane API (Chapter Lanes)."""

from __future__ import annotations

from pydantic import BaseModel

from backend.models.enums import QueueLaneState


class ChapterQueueStateUpdate(BaseModel):
    """Set a chapter lane to running / paused / overnight."""

    queue_state: QueueLaneState
