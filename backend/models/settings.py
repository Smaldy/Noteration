"""Settings — a single-row table (id is always 1) holding app configuration.

API keys are kept here for a local single-user app (a documented trade-off; see docs/architecture.md);
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
    # Which Gemini model the free-tier provider pins when rotation is OFF. One of
    # the four offered free-tier models (2.5/3.1 × flash/flash-lite). flash-lite is
    # the cheapest tier (no "thinking" overhead); the 3.1 tiers are newer/stronger.
    gemini_model: Mapped[str] = mapped_column(default="gemini-2.5-flash-lite")
    # Master switch for the whole Gemini tier. Turn off to force Ollama (e.g.
    # to test a local model's note quality). Default on.
    gemini_enabled: Mapped[bool] = mapped_column(default=True)
    # Model rotation. ON → cycle the four free-tier Gemini models, switching on each
    # model's per-model RPD limit (the shared token budget still falls through to
    # Ollama). OFF → use the single pinned ``gemini_model``. Default off (static).
    gemini_rotation: Mapped[bool] = mapped_column(default=False)
    # Overrides the default cheapest-first order; null = default order.
    provider_order: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    ollama_enabled: Mapped[bool] = mapped_column(default=False)
    # The local Ollama model name (e.g. "llama3.1"); null until the user picks one.
    # Ollama only serves when enabled *and* a model is set. With the two-model
    # local AI setup this is the legacy/manual-override slot; the setup flow
    # fills the two role fields below instead.
    ollama_model: Mapped[str | None] = mapped_column(default=None)
    # Two-model local AI (services/local_ai/): the fast model serves interactive
    # generation by default; the quality model serves overnight lanes always and
    # interactive when ``ollama_prefer_quality`` is on ("slower but higher
    # quality" toggle). Resolved pull tags, set by the install worker.
    ollama_fast_model: Mapped[str | None] = mapped_column(default=None)
    ollama_quality_model: Mapped[str | None] = mapped_column(default=None)
    ollama_prefer_quality: Mapped[bool] = mapped_column(default=False)
    # Manual pin: when set, this model serves EVERY local call (overnight and
    # interactive), overriding the fast/quality role split. Null = no pin.
    ollama_always_model: Mapped[str | None] = mapped_column(default=None)
    # Overnight batch generation uses Gemini instead of the local quality model.
    # Only takes effect when a Gemini key is configured and its tier is enabled;
    # interactive generation is unaffected. Default off (overnight stays local).
    overnight_use_gemini: Mapped[bool] = mapped_column(default=False)
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
    # Display face for headings; NULL keeps the built-in one (Montserrat).
    font_family_heading: Mapped[str | None] = mapped_column(default=None)
    font_size: Mapped[int] = mapped_column(default=16)
    # UI + AI-content language: "en" (default), "it", or "es". Drives the
    # frontend i18n and is injected into the generation prompts so new notes,
    # MCQs, and flashcards are produced in the chosen language. See
    # services/pipeline/generation.py.
    language: Mapped[str] = mapped_column(default="en")
    # The student's field of study — sets the AI tutor persona and what the
    # generated notes emphasise (formulas vs. themes vs. cases, …). One of
    # STUDY_FIELDS in services/pipeline/generation.py; "general" is neutral.
    # (The migration backfills pre-existing installs to "engineering", the
    # behavior they had when the persona was hardcoded.)
    study_field: Mapped[str] = mapped_column(default="general")
    # How the AI words the generated content: "balanced" (default, no extra
    # directive), "simple", "technical", "discursive", "concise", "academic".
    # See AI_STYLES in services/pipeline/generation.py.
    ai_style: Mapped[str] = mapped_column(default="balanced")
    # Assistant chat retention: "keep_last_5" (default, count-based — the
    # history list always caps at 5) or a time-based override: "after_1_hour",
    # "after_1_day", "on_close" (previous run's chats purged at startup).
    # Enforced in services/chat.py, driven by the queue worker's hooks.
    chat_retention: Mapped[str] = mapped_column(default="keep_last_5")
