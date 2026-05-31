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
from backend.models.enums import QueueStage, QueueState
from backend.models.hierarchy import utcnow

if TYPE_CHECKING:
    from backend.models.hierarchy import Topic


class QueueJob(Base):
    """One persistent job per topic sub-stage; sub-stages commit independently."""

    __tablename__ = "queue_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
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


class ProviderState(Base):
    """One row per waterfall provider — live budget and accumulated cost."""

    __tablename__ = "provider_states"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(unique=True)  # gemini_free / claude_paid / ...
    enabled: Mapped[bool] = mapped_column(default=True)
    order_index: Mapped[int] = mapped_column(default=0)  # waterfall position
    headroom: Mapped[int] = mapped_column(default=0)  # last probed remaining
    reset_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    supports_vision: Mapped[bool] = mapped_column(default=False)
    total_cost: Mapped[float] = mapped_column(default=0.0)
    total_tokens: Mapped[int] = mapped_column(default=0)
