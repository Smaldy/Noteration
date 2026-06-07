"""Exercise Duplicator — per-exercise ops: delete + find-more (Wave ED-7)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.duplicator import (
    DuplicateResult,
    ExerciseSession,
    ExtractedExercise,
)
from backend.models.enums import ExerciseStatus, QueueStage
from backend.models.processing import QueueJob
from backend.services.duplicator import sessions as sessionsvc


def _make_exercise(
    session: Session, *, status: ExerciseStatus = ExerciseStatus.done
) -> ExtractedExercise:
    es = ExerciseSession(document_hash="h", year_level=3)
    ex = ExtractedExercise(
        session=es,
        order_index=0,
        raw_text="Compute the residue of 1/(z^2+1) at z=i.",
        topic="complex_analysis.residues",
        status=status,
    )
    session.add(ex)
    session.commit()
    return ex


def test_delete_exercise_cascades_results_and_jobs(session: Session) -> None:
    ex = _make_exercise(session)
    session.add(DuplicateResult(exercise_id=ex.id, problem_text="Variant A"))
    session.add(QueueJob(stage=QueueStage.duplicate_search, exercise_id=ex.id))
    session.commit()
    ex_id = ex.id

    parent_id = sessionsvc.delete_exercise(session, ex_id)

    assert parent_id == ex.session_id
    assert session.get(ExtractedExercise, ex_id) is None
    # Results cascade (relationship); the pending search job cascades (FK).
    assert session.scalars(
        select(DuplicateResult).where(DuplicateResult.exercise_id == ex_id)
    ).all() == []
    assert session.scalars(
        select(QueueJob).where(QueueJob.exercise_id == ex_id)
    ).all() == []


def test_delete_exercise_unknown_id_raises(session: Session) -> None:
    with pytest.raises(sessionsvc.ExtractedExerciseNotFoundError):
        sessionsvc.delete_exercise(session, 999999)


def test_requeue_search_resets_status_and_enqueues(session: Session) -> None:
    ex = _make_exercise(session, status=ExerciseStatus.done)
    # An earlier search already produced one result — find-more must keep it.
    session.add(DuplicateResult(exercise_id=ex.id, problem_text="Existing variant"))
    session.commit()

    returned = sessionsvc.requeue_search(session, ex.id)

    assert returned.id == ex.session_id
    refreshed = session.get(ExtractedExercise, ex.id)
    assert refreshed is not None
    assert refreshed.status is ExerciseStatus.pending
    jobs = session.scalars(
        select(QueueJob).where(
            QueueJob.exercise_id == ex.id,
            QueueJob.stage == QueueStage.duplicate_search,
        )
    ).all()
    assert len(jobs) == 1
    # The prior result survives — a re-search appends, never clears.
    assert (
        session.scalars(
            select(DuplicateResult).where(DuplicateResult.exercise_id == ex.id)
        ).all()
        != []
    )


def test_requeue_search_unknown_id_raises(session: Session) -> None:
    with pytest.raises(sessionsvc.ExtractedExerciseNotFoundError):
        sessionsvc.requeue_search(session, 999999)
