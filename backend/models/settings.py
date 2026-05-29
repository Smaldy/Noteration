"""Settings — a single-row table (id is always 1) holding app configuration.

API keys are kept here for a local single-user app (acceptable per review.md);
they must never be written to logs or URLs.
"""

from __future__ import annotations

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base

SINGLETON_ID = 1


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=SINGLETON_ID)
    api_key_gemini: Mapped[str | None] = mapped_column(default=None)
    api_key_claude: Mapped[str | None] = mapped_column(default=None)
    # Hard "never spend" switch; false = free-only waterfall.
    allow_paid: Mapped[bool] = mapped_column(default=False)
    # Overrides the default cheapest-first order; null = default order.
    provider_order: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    ollama_enabled: Mapped[bool] = mapped_column(default=False)
    pomodoro_work_min: Mapped[int] = mapped_column(default=25)
    pomodoro_break_min: Mapped[int] = mapped_column(default=5)
    theme: Mapped[str] = mapped_column(default="system")
    accent_color: Mapped[str | None] = mapped_column(default=None)
    font_family: Mapped[str | None] = mapped_column(default=None)
    font_size: Mapped[int] = mapped_column(default=16)
