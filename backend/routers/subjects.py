"""Subjects router — list + create (Phase 9c).

Thin: delegates to ``services.subjects``. Exists so the upload flow can pick an
existing subject or create one before attaching a PDF.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models import Subject
from backend.schemas.subject import SubjectCreate, SubjectOut
from backend.services import subjects as subjectsvc

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("", response_model=list[SubjectOut])
def list_subjects(session: Session = Depends(get_session)) -> list[Subject]:
    """All subjects (name-sorted) for the upload picker."""
    return subjectsvc.list_subjects(session)


@router.post("", response_model=SubjectOut, status_code=201)
def create_subject(
    payload: SubjectCreate,
    session: Session = Depends(get_session),
) -> Subject:
    """Create a subject from the upload picker."""
    return subjectsvc.create_subject(
        session,
        name=payload.name,
        accent_color=payload.accent_color,
        exam_date=payload.exam_date,
    )
