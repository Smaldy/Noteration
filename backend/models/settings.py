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
    # Which Gemini model the free-tier provider calls. flash-lite is the cheapest
    # 2.5 tier (no "thinking" overhead); flash is more capable. (gemini-2.0-flash
    # was dropped — its free tier is now limit:0.)
    gemini_model: Mapped[str] = mapped_column(default="gemini-2.5-flash-lite")
    # Hard "never spend" switch; false = free-only waterfall.
    allow_paid: Mapped[bool] = mapped_column(default=False)
    # Overrides the default cheapest-first order; null = default order.
    provider_order: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    ollama_enabled: Mapped[bool] = mapped_column(default=False)
    # Per-document token ceiling (defense-in-depth against a runaway document).
    # 0 = automatic budget (estimate × overspend factor); a positive value is a
    # flat ceiling. See services/queue.py.
    per_document_token_budget: Mapped[int] = mapped_column(default=0)
    # How much notes content to generate per topic, in "pages" (units of content,
    # ~300 words each). 1-10; the model is asked to aim for this many pages and to
    # produce only what the source supports when there isn't enough material. See
    # services/pipeline/generation.py.
    note_length: Mapped[int] = mapped_column(default=3)
    pomodoro_work_min: Mapped[int] = mapped_column(default=25)
    pomodoro_break_min: Mapped[int] = mapped_column(default=5)
    # Calendar hourly Day view: the visible hour window [start, end) and the slot
    # gap in minutes (e.g. 60 = one row per hour, 30 = half-hour rows).
    calendar_day_start_hour: Mapped[int] = mapped_column(default=8)
    calendar_day_end_hour: Mapped[int] = mapped_column(default=23)
    calendar_slot_minutes: Mapped[int] = mapped_column(default=60)
    theme: Mapped[str] = mapped_column(default="system")
    accent_color: Mapped[str | None] = mapped_column(default=None)
    font_family: Mapped[str | None] = mapped_column(default=None)
    font_size: Mapped[int] = mapped_column(default=16)
    # UI + AI-content language: "en" (default), "it", or "es". Drives the
    # frontend i18n and is injected into the generation prompts so new notes,
    # MCQs, and flashcards are produced in the chosen language. See
    # services/pipeline/generation.py.
    language: Mapped[str] = mapped_column(default="en")
