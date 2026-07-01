"""Schemas for the Settings API (Phase 9f).

API keys are write-only: the client can set them, but ``SettingsOut`` only
reports whether each is present (never echoes the secret back).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.models.settings import Settings

Theme = Literal["system", "light", "dark"]
# Allowed slot gaps (minutes) for the calendar's hourly Day view.
CalendarSlot = Literal[15, 30, 60, 90, 120]
# The free-tier Gemini models the user may pin when rotation is OFF. flash-lite is
# cheapest; flash is more capable; the 3.1 generation is newer/stronger than 2.5.
GeminiModel = Literal[
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
]
# UI + AI-content language. "en" is the default; the AI is asked to generate new
# notes/MCQs/flashcards in the chosen language (see services/pipeline/generation.py).
Language = Literal["en", "it", "es"]


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    allow_paid: bool
    provider_order: list[str] | None
    ollama_enabled: bool
    ollama_model: str | None
    gemini_model: str
    gemini_enabled: bool
    gemini_rotation: bool
    per_document_token_budget: int
    note_length: int
    pomodoro_work_min: int
    pomodoro_break_min: int
    calendar_day_start_hour: int
    calendar_day_end_hour: int
    calendar_slot_minutes: int
    theme: str
    accent_color: str | None
    font_family: str | None
    font_size: int
    language: str
    # Derived — keys are never echoed back.
    gemini_key_set: bool
    claude_key_set: bool

    @classmethod
    def from_model(cls, settings: Settings) -> SettingsOut:
        return cls(
            allow_paid=settings.allow_paid,
            provider_order=settings.provider_order,
            ollama_enabled=settings.ollama_enabled,
            ollama_model=settings.ollama_model,
            gemini_model=settings.gemini_model,
            gemini_enabled=settings.gemini_enabled,
            gemini_rotation=settings.gemini_rotation,
            per_document_token_budget=settings.per_document_token_budget,
            note_length=settings.note_length,
            pomodoro_work_min=settings.pomodoro_work_min,
            pomodoro_break_min=settings.pomodoro_break_min,
            calendar_day_start_hour=settings.calendar_day_start_hour,
            calendar_day_end_hour=settings.calendar_day_end_hour,
            calendar_slot_minutes=settings.calendar_slot_minutes,
            theme=settings.theme,
            accent_color=settings.accent_color,
            font_family=settings.font_family,
            font_size=settings.font_size,
            language=settings.language,
            gemini_key_set=bool(settings.api_key_gemini),
            claude_key_set=bool(settings.api_key_claude),
        )


class SettingsUpdate(BaseModel):
    """Partial update — only fields present in the request are applied.

    For ``api_key_*``, an empty string clears the stored key; a non-empty string
    sets it; omitting the field leaves it unchanged.
    """

    api_key_gemini: str | None = None
    api_key_claude: str | None = None
    allow_paid: bool | None = None
    provider_order: list[str] | None = None
    ollama_enabled: bool | None = None
    # Empty string clears the stored Ollama model name; a non-empty string sets it.
    ollama_model: str | None = None
    gemini_model: GeminiModel | None = None
    gemini_enabled: bool | None = None
    gemini_rotation: bool | None = None
    # 0 = automatic ceiling (estimate × factor); a positive value is a flat cap.
    per_document_token_budget: int | None = Field(default=None, ge=0)
    # Notes length in "pages" (units of content) per topic; 1-10.
    note_length: int | None = Field(default=None, ge=1, le=10)
    pomodoro_work_min: int | None = Field(default=None, ge=1, le=180)
    pomodoro_break_min: int | None = Field(default=None, ge=1, le=120)
    # Hourly Day-view window. end must exceed start; the calendar clamps too.
    calendar_day_start_hour: int | None = Field(default=None, ge=0, le=23)
    calendar_day_end_hour: int | None = Field(default=None, ge=1, le=24)
    calendar_slot_minutes: CalendarSlot | None = None
    theme: Theme | None = None
    accent_color: str | None = None
    font_family: str | None = None
    font_size: int | None = Field(default=None, ge=10, le=32)
    language: Language | None = None

    @model_validator(mode="after")
    def _day_window_ordered(self) -> SettingsUpdate:
        if (
            self.calendar_day_start_hour is not None
            and self.calendar_day_end_hour is not None
            and self.calendar_day_end_hour <= self.calendar_day_start_hour
        ):
            raise ValueError(
                "calendar_day_end_hour must be greater than calendar_day_start_hour"
            )
        return self
