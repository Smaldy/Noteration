"""Exercise Duplicator router — upload/extract sessions and read them back."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.schemas.duplicator import ExerciseSessionOut
from backend.services.documents import InvalidPDFError
from backend.services.duplicator import sessions as sessionsvc
from backend.services.providers.base import AllProvidersExhausted

router = APIRouter(prefix="/duplicator", tags=["duplicator"])


@router.post("/sessions", response_model=ExerciseSessionOut, status_code=201)
async def create_session(
    file: UploadFile = File(...),
    year_level: int = Form(..., ge=1, le=5),
    subject_hint: str | None = Form(None),
    session: Session = Depends(get_session),
) -> ExerciseSessionOut:
    """Upload an exercise PDF → extract its exercises synchronously.

    422 when ``year_level`` is out of 1–5 or the file isn't a PDF; 503 when no
    provider has headroom for the vision extraction call.
    """
    data = await file.read()
    try:
        exercise_session = sessionsvc.create_session(
            session,
            data=data,
            filename=file.filename or "exercises.pdf",
            year_level=year_level,
            subject_hint=subject_hint,
        )
    except InvalidPDFError:
        raise HTTPException(status_code=422, detail="Uploaded file is not a PDF")
    except AllProvidersExhausted as exc:
        raise HTTPException(
            status_code=503,
            detail=exc.reason or "No AI provider has headroom right now",
        )
    return ExerciseSessionOut.model_validate(exercise_session)


@router.get("/sessions/{session_id}", response_model=ExerciseSessionOut)
def get_session_detail(
    session_id: int,
    session: Session = Depends(get_session),
) -> ExerciseSessionOut:
    """Return a session with its exercises and any duplicate results found so far."""
    try:
        exercise_session = sessionsvc.get_exercise_session(session, session_id)
    except sessionsvc.ExerciseSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Exercise session not found")
    return ExerciseSessionOut.model_validate(exercise_session)
