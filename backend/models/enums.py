"""Shared enums for the ORM, exactly per docs/data-model.md.

Stored as plain strings (``native_enum=False``) and validated in Python via
these ``StrEnum`` classes — SQLite has no native enum type.
"""

import enum


class DocumentStatus(enum.StrEnum):
    uploaded = "uploaded"
    processing = "processing"
    ready = "ready"
    error = "error"


class DocumentMode(enum.StrEnum):
    """How a document is processed and presented.

    ``study`` (default) is the full pipeline: notes + MCQs + flashcards, with the
    formula vision stage. ``exam`` is assessment-only — the generation call drops
    notes and the formula stage is skipped, so the document yields just MCQs (with
    explanations) and flashcards. Drives the dedicated Exam Prep section.
    """

    study = "study"
    exam = "exam"


class TopicPriority(enum.StrEnum):
    exam_critical = "exam_critical"
    medium = "medium"
    skip = "skip"  # never sent to a model


class TopicStatus(enum.StrEnum):
    queued = "queued"
    processing = "processing"
    ready = "ready"
    error = "error"


class QueueStage(enum.StrEnum):
    formula = "formula"
    notes = "notes"
    assessment = "assessment"


class QueueState(enum.StrEnum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"


class FormulaState(enum.StrEnum):
    pending = "pending"  # region detected/registered; vision transcription deferred
    reconstructed = "reconstructed"
    verified = "verified"


class ScheduleSource(enum.StrEnum):
    sm2 = "sm2"
    manual = "manual"
    deadline = "deadline"
