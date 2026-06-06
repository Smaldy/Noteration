"""Schemas for the Exercise Duplicator API (sessions + exercises + results).

``VizBlock`` mirrors the renderer contract the frontend reads (``viz.type`` routes
to a renderer). It's kept permissive — a model may emit any of the documented
types plus the renderer-specific ``expression`` / ``domain`` / ``params`` — so the
backend never rejects an otherwise-usable exercise over a viz field.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.models.enums import ExerciseSessionStatus, ExerciseStatus


class DuplicateResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_url: str | None
    problem_text: str
    viz: dict[str, Any] | None
    difficulty_score: float | None


class ExtractedExerciseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_index: int
    raw_text: str
    topic: str
    subtopic: str | None
    difficulty_signals: list[str]
    viz: dict[str, Any] | None
    status: ExerciseStatus
    results: list[DuplicateResultOut] = []


class ExerciseSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_hash: str
    year_level: int
    subject_hint: str | None
    status: ExerciseSessionStatus
    exercises: list[ExtractedExerciseOut] = []
