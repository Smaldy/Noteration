"""Exercise Duplicator models — the three-stage hybrid pipeline (Option C).

An ``ExerciseSession`` is one uploaded exercise PDF. Stage 1 extracts its
``ExtractedExercise`` rows synchronously (vision model). Stage 2 searches for
real university-level variants per exercise on the background queue, writing
``DuplicateResult`` rows. ``CalibrationSample`` accumulates topic+year examples
(from the user's own uploads, ``own``, or an ``import``) that ground the search
prompt. Cascade deletes run session → exercises → results.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base
from backend.db.types import UTCDateTime
from backend.models.enums import (
    CalibrationSource,
    ExerciseSessionStatus,
    ExerciseStatus,
)
from backend.models.hierarchy import utcnow


class ExerciseSession(Base):
    """One uploaded exercise PDF and its extraction state."""

    __tablename__ = "exercise_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # SHA-256 of the PDF — matches the ingestion cache key (cache/<hash>/...).
    document_hash: Mapped[str]
    year_level: Mapped[int]  # 1–5, user-selected (validated at the API boundary)
    subject_hint: Mapped[str | None] = mapped_column(default=None)
    status: Mapped[ExerciseSessionStatus] = mapped_column(
        SAEnum(ExerciseSessionStatus, native_enum=False),
        default=ExerciseSessionStatus.extracting,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    exercises: Mapped[list[ExtractedExercise]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ExtractedExercise(Base):
    """One exercise lifted from the PDF, plus its variant-search state."""

    __tablename__ = "extracted_exercises"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("exercise_sessions.id", ondelete="CASCADE")
    )
    order_index: Mapped[int] = mapped_column(default=0)
    raw_text: Mapped[str]
    topic: Mapped[str]  # dot notation, e.g. "complex_analysis.residues"
    subtopic: Mapped[str | None] = mapped_column(default=None)
    # list[str] of difficulty keywords lifted from the problem.
    difficulty_signals: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Viz block (see the feature spec) when a visual aids solving; else None.
    viz: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    status: Mapped[ExerciseStatus] = mapped_column(
        SAEnum(ExerciseStatus, native_enum=False), default=ExerciseStatus.pending
    )

    session: Mapped[ExerciseSession] = relationship(back_populates="exercises")
    results: Mapped[list[DuplicateResult]] = relationship(
        back_populates="exercise", cascade="all, delete-orphan"
    )


class DuplicateResult(Base):
    """A real university-level variant problem found for an exercise."""

    __tablename__ = "duplicate_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("extracted_exercises.id", ondelete="CASCADE")
    )
    source_url: Mapped[str | None] = mapped_column(default=None)
    problem_text: Mapped[str]
    viz: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    difficulty_score: Mapped[float | None] = mapped_column(default=None)  # 0.0–1.0
    # The search job that produced this result. SET NULL so a result survives the
    # queue job being pruned; nullable for manually-added/imported results.
    queue_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("queue_jobs.id", ondelete="SET NULL"), default=None
    )

    exercise: Mapped[ExtractedExercise] = relationship(back_populates="results")


class CalibrationSample(Base):
    """A topic+year example used to ground the variant-search prompt."""

    __tablename__ = "calibration_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str]
    subtopic: Mapped[str | None] = mapped_column(default=None)
    year_level: Mapped[int]
    source_text: Mapped[str]
    source: Mapped[CalibrationSource] = mapped_column(
        SAEnum(CalibrationSource, native_enum=False), default=CalibrationSource.own
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
