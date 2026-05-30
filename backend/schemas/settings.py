"""Schemas for the Settings API (Phase 9f).

API keys are write-only: the client can set them, but ``SettingsOut`` only
reports whether each is present (never echoes the secret back).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.models.settings import Settings

Theme = Literal["system", "light", "dark"]


class SettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    allow_paid: bool
    provider_order: list[str] | None
    ollama_enabled: bool
    pomodoro_work_min: int
    pomodoro_break_min: int
    theme: str
    accent_color: str | None
    font_family: str | None
    font_size: int
    # Derived — keys are never echoed back.
    gemini_key_set: bool
    claude_key_set: bool

    @classmethod
    def from_model(cls, settings: Settings) -> "SettingsOut":
        return cls(
            allow_paid=settings.allow_paid,
            provider_order=settings.provider_order,
            ollama_enabled=settings.ollama_enabled,
            pomodoro_work_min=settings.pomodoro_work_min,
            pomodoro_break_min=settings.pomodoro_break_min,
            theme=settings.theme,
            accent_color=settings.accent_color,
            font_family=settings.font_family,
            font_size=settings.font_size,
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
    pomodoro_work_min: int | None = Field(default=None, ge=1, le=180)
    pomodoro_break_min: int | None = Field(default=None, ge=1, le=120)
    theme: Theme | None = None
    accent_color: str | None = None
    font_family: str | None = None
    font_size: int | None = Field(default=None, ge=10, le=32)
