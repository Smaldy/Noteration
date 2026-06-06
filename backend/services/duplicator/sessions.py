"""Exercise Duplicator session orchestration (Stage 1 driver).

``create_session`` ingests the uploaded exercise PDF (reusing the content-hash
cache), creates an ``ExerciseSession``, runs synchronous extraction, and — in
later waves — enqueues a ``duplicate_search`` job per exercise (ED-3) and records
each exercise as an ``own`` calibration sample (ED-4). The whole thing commits in
one transaction so a session is never persisted half-built.

``get_exercise_session`` loads a session with its exercises + results eagerly, for
the GET endpoint. (Named to avoid colliding with the ``get_session`` DB
dependency.)
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models.duplicator import ExerciseSession, ExtractedExercise
from backend.models.enums import ExerciseSessionStatus, QueueStage
from backend.models.processing import QueueJob
from backend.services.documents import PDF_MAGIC, InvalidPDFError, _persist_upload
from backend.services.duplicator.extraction import (
    PageLoader,
    extract_exercises,
    load_page_images,
)
from backend.services.pipeline.ingestion import UPLOADS_DIR, IngestionResult, ingest
from backend.services.providers.factory import build_waterfall_from_settings
from backend.services.providers.waterfall import Waterfall
from backend.services.settings import get_settings

IngestFn = Callable[[Path], IngestionResult]


class ExerciseSessionNotFoundError(LookupError):
    """The requested exercise session does not exist."""


def create_session(
    session: Session,
    *,
    data: bytes,
    filename: str,
    year_level: int,
    subject_hint: str | None,
    waterfall: Waterfall | None = None,
    ingest_fn: IngestFn = ingest,
    uploads_dir: str | Path = UPLOADS_DIR,
    load_pages: PageLoader = load_page_images,
) -> ExerciseSession:
    """Ingest the PDF, extract its exercises synchronously, and persist atomically.

    Raises ``InvalidPDFError`` for non-PDF bytes. Provider-exhaustion errors from
    extraction propagate (the router maps them to 503); nothing is committed in
    that case. ``waterfall`` / ``ingest_fn`` are injectable for tests.
    """
    if not data.startswith(PDF_MAGIC):
        raise InvalidPDFError("uploaded file is not a PDF")

    pdf_path = _persist_upload(data, Path(uploads_dir))
    result = ingest_fn(pdf_path)

    exercise_session = ExerciseSession(
        document_hash=result.file_hash,
        year_level=year_level,
        subject_hint=(subject_hint.strip() if subject_hint and subject_hint.strip() else None),
        status=ExerciseSessionStatus.extracting,
    )
    session.add(exercise_session)
    session.flush()

    if waterfall is None:
        waterfall = build_waterfall_from_settings(get_settings(session))

    exercises = extract_exercises(
        session, exercise_session, waterfall, load_pages=load_pages
    )

    # One topic-less duplicate_search job per exercise (drained by the dedicated
    # search loop, never the generation lane). ED-4 will also record each exercise
    # as an `own` CalibrationSample here, in this same transaction.
    for exercise in exercises:
        session.add(
            QueueJob(stage=QueueStage.duplicate_search, exercise_id=exercise.id)
        )

    session.commit()
    session.refresh(exercise_session)
    return exercise_session


def get_exercise_session(session: Session, session_id: int) -> ExerciseSession:
    """Load a session with exercises + their duplicate results eagerly.

    Raises ``ExerciseSessionNotFoundError`` when the id is unknown.
    """
    exercise_session = session.scalars(
        select(ExerciseSession)
        .where(ExerciseSession.id == session_id)
        .options(
            selectinload(ExerciseSession.exercises).selectinload(
                ExtractedExercise.results
            )
        )
    ).one_or_none()
    if exercise_session is None:
        raise ExerciseSessionNotFoundError(session_id)
    return exercise_session
