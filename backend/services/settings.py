"""Settings service — read + partial update of the singleton row."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from backend.models.settings import SINGLETON_ID, Settings

# API-key fields where an empty string means "clear the stored key".
_KEY_FIELDS = {"api_key_gemini", "api_key_claude"}


def get_settings(session: Session) -> Settings:
    """Return the settings singleton, creating it with defaults if absent."""
    settings = session.get(Settings, SINGLETON_ID)
    if settings is None:
        settings = Settings(id=SINGLETON_ID)
        session.add(settings)
        session.commit()
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
