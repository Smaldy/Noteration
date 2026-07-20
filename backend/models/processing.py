"""Persistent processing state: QueueJob (per-topic) and ProviderState.

These make the queue survive restarts and limit windows — the reliability core
built out in Phases 3–4. Models only here; behavior comes later.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base
from backend.db.types import UTCDateTime
from backend.models.enums import HistoryEventType, QueueStage, QueueState
from backend.models.hierarchy import utcnow

if TYPE_CHECKING:
    from backend.models.hierarchy import Topic


class QueueJob(Base):
    """One persistent job per topic sub-stage; sub-stages commit independently."""

    __tablename__ = "queue_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable because Exercise Duplicator ``duplicate_search`` jobs have no topic
    # (they carry ``exercise_id`` instead). Generation jobs always set both.
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), default=None
    )
    # Denormalized lane key (Wave B): the job's subject, via Topic→Chapter→Subject.
    # Set on enqueue and kept consistent on write so per-subject lane queries
    # (claim/arbitrate/pause) don't join the whole hierarchy each time. Null for
    # topic-less ``duplicate_search`` jobs (they never enter the lane path).
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), default=None
    )
    # Set ONLY on ``duplicate_search`` jobs: the exercise to find variants for.
    # CASCADE so deleting the exercise/session cleans up its pending search job.
    exercise_id: Mapped[int | None] = mapped_column(
        ForeignKey("extracted_exercises.id", ondelete="CASCADE"), default=None
    )
    stage: Mapped[QueueStage] = mapped_column(SAEnum(QueueStage, native_enum=False))
    state: Mapped[QueueState] = mapped_column(
        SAEnum(QueueState, native_enum=False), default=QueueState.pending
    )
    attempts: Mapped[int] = mapped_column(default=0)  # → error after N
    assigned_provider: Mapped[str | None] = mapped_column(default=None)
    est_tokens: Mapped[int] = mapped_column(default=0)  # for budget dispatch
    tokens_used: Mapped[int] = mapped_column(default=0)  # actual spend (in+out)
    last_error: Mapped[str | None] = mapped_column(default=None)
    # Set when a provider limit defers the job to a reset window.
    resume_after: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow
    )

    topic: Mapped[Topic] = relationship(back_populates="queue_jobs")


class HistoryEvent(Base):
    """Append-only log of notable generation events (Wave C).

    The cost-visibility/transparency surface that replaces overnight notifications.
    ``subject_id``/``topic_id`` are nullable (global events like a provider switch
    aren't tied to a subject) and ``SET NULL`` on delete so the log survives the
    deletion of what it references.
    """

    __tablename__ = "history_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="SET NULL"), default=None
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), default=None
    )
    event_type: Mapped[HistoryEventType] = mapped_column(
        SAEnum(HistoryEventType, native_enum=False)
    )
    provider_from: Mapped[str | None] = mapped_column(default=None)
    provider_to: Mapped[str | None] = mapped_column(default=None)
    detail: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ProviderState(Base):
    """One row per waterfall provider — live budget and accumulated cost."""

    __tablename__ = "provider_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(unique=True)  # gemini_free / ollama / ...
    enabled: Mapped[bool] = mapped_column(default=True)
    order_index: Mapped[int] = mapped_column(default=0)  # waterfall position
    headroom: Mapped[int] = mapped_column(default=0)  # last probed remaining
    reset_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    supports_vision: Mapped[bool] = mapped_column(default=False)
    total_cost: Mapped[float] = mapped_column(default=0.0)
    total_tokens: Mapped[int] = mapped_column(default=0)
