"""Settings service — read + partial update of the singleton row."""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.settings import SINGLETON_ID, Settings

# Fields where an empty string means "clear the stored value" (store NULL): the
# API keys, plus the optional Ollama model names (empty = role unassigned).
_KEY_FIELDS = {
    "api_key_gemini",
    "api_key_claude",
    "ollama_model",
    "ollama_fast_model",
    "ollama_quality_model",
    "ollama_always_model",
}


def get_settings(session: Session) -> Settings:
    """Return the settings singleton, creating it with defaults if absent.

    On a fresh install the frontend boot calls and the background worker can all
    try to create the singleton at once; the first INSERT wins and the others hit
    a UNIQUE violation. We treat that as "someone else created it" and re-read,
    so first launch never surfaces an error.
    """
    settings = session.get(Settings, SINGLETON_ID)
    if settings is not None:
        return settings
    settings = Settings(id=SINGLETON_ID)
    session.add(settings)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return session.get(Settings, SINGLETON_ID)
    session.refresh(settings)
    return settings


def update_settings(session: Session, changes: dict[str, Any]) -> Settings:
    """Apply only the provided fields (an empty API key clears it), then commit."""
    settings = get_settings(session)
    for field, value in changes.items():
        if field in _KEY_FIELDS and not value:
            value = None  # empty/blank string clears the key
        setattr(settings, field, value)
    session.commit()
    session.refresh(settings)
    return settings
