"""Local AI setup state — a single-row table (id is always 1).

Persists the detect → confirm → install lifecycle so the flow survives a
restart: a row found in ``installing_ollama``/``pulling`` on boot is simply
resumed by the install worker (Ollama pulls continue from partial layers, so
resuming loses nothing). The ``hardware``/``selection`` JSON snapshots are
what Stage 5's confirm screen (and the copy-detection-report button) render.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base
from backend.db.types import UTCDateTime
from backend.models.enums import LocalAiStatus
from backend.models.hierarchy import utcnow

SETUP_ID = 1


class LocalAiSetup(Base):
    __tablename__ = "local_ai_setup"

    id: Mapped[int] = mapped_column(primary_key=True, default=SETUP_ID)
    status: Mapped[LocalAiStatus] = mapped_column(
        SAEnum(LocalAiStatus, native_enum=False), default=LocalAiStatus.not_configured
    )
    # Snapshots from the last detection run (dataclass dumps of HardwareProfile
    # and SelectionResult) — what the confirm screen shows and the user overrides.
    hardware: Mapped[dict | None] = mapped_column(JSON, default=None)
    selection: Mapped[dict | None] = mapped_column(JSON, default=None)
    # What the user confirmed to install: {"quality": {"tag", "quant"}, "fast":
    # {...}}. Quant→pull-tag resolution happens at install time (it needs the
    # registry), so this stores the intent, not the final tag.
    chosen: Mapped[dict | None] = mapped_column(JSON, default=None)
    # The resolved Ollama tags actually pulled (mirrors what lands in Settings).
    quality_model: Mapped[str | None] = mapped_column(default=None)
    fast_model: Mapped[str | None] = mapped_column(default=None)
    # Live pull progress for the status endpoint (bytes of the current tag).
    pull_tag: Mapped[str | None] = mapped_column(default=None)
    pull_completed: Mapped[int] = mapped_column(default=0)
    pull_total: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(default=None)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow
    )
