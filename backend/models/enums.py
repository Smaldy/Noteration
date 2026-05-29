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
    reconstructed = "reconstructed"
    verified = "verified"


class ScheduleSource(enum.StrEnum):
    sm2 = "sm2"
    manual = "manual"
    deadline = "deadline"
