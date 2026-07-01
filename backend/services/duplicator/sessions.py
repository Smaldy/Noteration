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
from backend.models.enums import ExerciseSessionStatus, ExerciseStatus, QueueStage
from backend.models.processing import QueueJob
from backend.paths import UPLOADS_DIR
from backend.services.documents import PDF_MAGIC, InvalidPDFError, _persist_upload
from backend.services.duplicator.calibration import add_sample
from backend.services.duplicator.extraction import (
    PageLoader,
    extract_exercises,
    load_page_images,
)
from backend.services.pipeline.ingestion import IngestionResult, ingest
from backend.services.providers.factory import build_waterfall_from_settings
from backend.services.providers.waterfall import Waterfall
from backend.services.settings import get_settings

IngestFn = Callable[[Path], IngestionResult]


class ExerciseSessionNotFoundError(LookupError):
    """The requested exercise session does not exist."""


class ExtractedExerciseNotFoundError(LookupError):
    """The requested extracted exercise does not exist."""


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

    # Per exercise: a topic-less duplicate_search job (drained by the dedicated
    # search loop, never the generation lane) and an `own` calibration sample —
    # all inside this one transaction.
    for exercise in exercises:
        session.add(
            QueueJob(stage=QueueStage.duplicate_search, exercise_id=exercise.id)
        )
        add_sample(
            session,
            topic=exercise.topic,
            subtopic=exercise.subtopic,
            year_level=exercise_session.year_level,
            source_text=exercise.raw_text,
            commit=False,
        )

    session.commit()
    session.refresh(exercise_session)
    return exercise_session


def delete_exercise(session: Session, exercise_id: int) -> int:
    """Delete one extracted exercise (cascading its results + queue jobs).

    Returns the parent ``session_id`` so the caller can report back which session
    changed. Raises ``ExtractedExerciseNotFoundError`` for an unknown id. Results
    cascade via the relationship; any pending ``duplicate_search`` job cascades via
    the FK ``ondelete=CASCADE`` on ``QueueJob.exercise_id``.
    """
    exercise = session.get(ExtractedExercise, exercise_id)
    if exercise is None:
        raise ExtractedExerciseNotFoundError(exercise_id)
    session_id = exercise.session_id
    session.delete(exercise)
    session.commit()
    return session_id


def requeue_search(session: Session, exercise_id: int) -> ExerciseSession:
    """Enqueue another ``duplicate_search`` for an exercise ("find more variants").

    Resets the exercise to ``pending`` (so the search drain re-claims it) and adds
    a fresh search job; the processor *appends* new ``DuplicateResult`` rows to the
    ones already found. Returns the reloaded parent session for the caller to send
    back. Raises ``ExtractedExerciseNotFoundError`` for an unknown id.
    """
    exercise = session.get(ExtractedExercise, exercise_id)
    if exercise is None:
        raise ExtractedExerciseNotFoundError(exercise_id)
    exercise.status = ExerciseStatus.pending
    session.add(
        QueueJob(stage=QueueStage.duplicate_search, exercise_id=exercise.id)
    )
    session.commit()
    return get_exercise_session(session, exercise.session_id)


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
