"""Exercise Duplicator router — upload/extract sessions and read them back."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.schemas.duplicator import (
    CalibrationImportResult,
    CalibrationSampleIn,
    ExerciseSessionOut,
)
from backend.services.documents import InvalidPDFError
from backend.services.duplicator import calibration as calibrationsvc
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


@router.get("/calibration/export")
def export_calibration(session: Session = Depends(get_session)) -> JSONResponse:
    """Download the calibration corpus as a JSON file."""
    payload = calibrationsvc.export_calibration(session)
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": "attachment; filename=noteration-calibration.json"
        },
    )


@router.post("/calibration/import", response_model=CalibrationImportResult)
async def import_calibration(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> CalibrationImportResult:
    """Import a calibration JSON file. 422 when the file isn't valid JSON."""
    raw = await file.read()
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=422, detail="File is not valid JSON")
    imported, skipped = calibrationsvc.import_calibration(session, data)
    return CalibrationImportResult(imported=imported, skipped=skipped)


@router.post("/calibration/samples", status_code=201)
def add_calibration_sample(
    payload: CalibrationSampleIn,
    session: Session = Depends(get_session),
) -> dict[str, int]:
    """Save one variant as a calibration sample (the variant-card button)."""
    sample = calibrationsvc.add_sample(
        session,
        topic=payload.topic,
        subtopic=payload.subtopic,
        year_level=payload.year_level,
        source_text=payload.source_text,
    )
    return {"id": sample.id}


@router.post(
    "/exercises/{exercise_id}/search", response_model=ExerciseSessionOut
)
def find_more_variants(
    exercise_id: int,
    session: Session = Depends(get_session),
) -> ExerciseSessionOut:
    """Queue another variant search for one exercise ("Find more variants").

    Resets the exercise to pending and enqueues a fresh ``duplicate_search`` job;
    the background worker drains it and appends new results. 404 for an unknown id.
    """
    try:
        exercise_session = sessionsvc.requeue_search(session, exercise_id)
    except sessionsvc.ExtractedExerciseNotFoundError:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return ExerciseSessionOut.model_validate(exercise_session)


@router.delete("/exercises/{exercise_id}", status_code=204)
def delete_exercise(
    exercise_id: int,
    session: Session = Depends(get_session),
) -> None:
    """Remove one extracted exercise and its variant results. 404 for unknown id."""
    try:
        sessionsvc.delete_exercise(session, exercise_id)
    except sessionsvc.ExtractedExerciseNotFoundError:
        raise HTTPException(status_code=404, detail="Exercise not found")


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
