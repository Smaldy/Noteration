"""Settings router — read + partial update of the app settings singleton."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.schemas.settings import SettingsOut, SettingsUpdate
from backend.services import settings as settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
def read_settings(session: Session = Depends(get_session)) -> SettingsOut:
    """Current settings (API keys reported as set/unset, never echoed)."""
    return SettingsOut.from_model(settings_service.get_settings(session))


@router.patch("", response_model=SettingsOut)
def patch_settings(
    payload: SettingsUpdate,
    session: Session = Depends(get_session),
) -> SettingsOut:
    """Apply a partial update — only fields present in the body change."""
    changes = payload.model_dump(exclude_unset=True)
    settings = settings_service.update_settings(session, changes)
    return SettingsOut.from_model(settings)
