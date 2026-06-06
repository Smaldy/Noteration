"""Exercise Duplicator model tests (Wave ED-1).

Round-trip each of the four tables, the cascade chain
(session → exercises → results), the queue-job SET NULL link, and FK
enforcement — mirroring test_models.py conventions on the in-memory DB.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import (
    CalibrationSample,
    Chapter,
    Document,
    DuplicateResult,
    ExerciseSession,
    ExtractedExercise,
    QueueJob,
    Subject,
    Topic,
)
from backend.models.enums import (
    CalibrationSource,
    ExerciseSessionStatus,
    ExerciseStatus,
    QueueStage,
)


def _make_exercise(session: Session) -> ExtractedExercise:
    sess = ExerciseSession(document_hash="abc123", year_level=3)
    ex = ExtractedExercise(
        session=sess,
        order_index=0,
        raw_text="Compute the residue of 1/(z^2+1) at z=i.",
        topic="complex_analysis.residues",
    )
    session.add(ex)
    session.commit()
    return ex


def test_exercise_session_roundtrip_and_defaults(session: Session) -> None:
    sess = ExerciseSession(document_hash="deadbeef", year_level=2)
    session.add(sess)
    session.commit()
    fetched = session.scalars(select(ExerciseSession)).one()
    assert fetched.document_hash == "deadbeef"
    assert fetched.year_level == 2
    assert fetched.subject_hint is None
    assert fetched.status is ExerciseSessionStatus.extracting
    assert fetched.created_at is not None


def test_extracted_exercise_json_and_defaults(session: Session) -> None:
    sess = ExerciseSession(document_hash="h", year_level=1, subject_hint="topology")
    ex = ExtractedExercise(
        session=sess,
        order_index=2,
        raw_text="Prove every compact metric space is complete.",
        topic="topology.compactness",
        subtopic="completeness",
        difficulty_signals=["proof", "metric_space"],
        viz=None,
    )
    session.add(ex)
    session.commit()
    fetched = session.scalars(select(ExtractedExercise)).one()
    assert fetched.difficulty_signals == ["proof", "metric_space"]
    assert fetched.viz is None
    assert fetched.subtopic == "completeness"
    assert fetched.status is ExerciseStatus.pending
    assert sess.subject_hint == "topology"


def test_extracted_exercise_viz_block_round_trips(session: Session) -> None:
    sess = ExerciseSession(document_hash="h", year_level=2)
    viz = {"type": "mafs_function", "expression": "x^3 - 4*x + 2", "domain": [-5, 5]}
    ex = ExtractedExercise(
        session=sess, raw_text="Graph f.", topic="calculus.functions", viz=viz
    )
    session.add(ex)
    session.commit()
    session.expire(ex)
    assert ex.viz == viz


def test_duplicate_result_roundtrip_and_defaults(session: Session) -> None:
    ex = _make_exercise(session)
    result = DuplicateResult(
        exercise=ex,
        problem_text="Find the residue of cot(z) at z=0.",
        difficulty_score=0.72,
    )
    session.add(result)
    session.commit()
    fetched = session.scalars(select(DuplicateResult)).one()
    assert fetched.problem_text.startswith("Find the residue")
    assert fetched.source_url is None
    assert fetched.viz is None
    assert fetched.difficulty_score == pytest.approx(0.72)
    assert fetched.queue_job_id is None


def test_calibration_sample_default_source_is_own(session: Session) -> None:
    sample = CalibrationSample(
        topic="abstract_algebra.subgroups",
        year_level=3,
        source_text="Show that the center of a group is a normal subgroup.",
    )
    session.add(sample)
    session.commit()
    assert sample.source is CalibrationSource.own
    assert sample.created_at is not None


def test_calibration_sample_imported_value_is_import(session: Session) -> None:
    sample = CalibrationSample(
        topic="t",
        year_level=1,
        source_text="x",
        source=CalibrationSource.imported,
    )
    session.add(sample)
    session.commit()
    session.expire(sample)
    assert sample.source is CalibrationSource.imported
    # SAEnum stores the member *name* (repo convention: name == value).
    raw = session.connection().exec_driver_sql(
        "SELECT source FROM calibration_samples"
    ).scalar()
    assert raw == "imported"


def test_cascade_delete_session_removes_exercises_and_results(session: Session) -> None:
    ex = _make_exercise(session)
    session.add(DuplicateResult(exercise=ex, problem_text="variant"))
    session.commit()
    sess = session.scalars(select(ExerciseSession)).one()

    session.delete(sess)
    session.commit()
    for model in (ExtractedExercise, DuplicateResult):
        assert session.scalars(select(model)).all() == []


def test_queue_job_delete_nulls_result_link(session: Session) -> None:
    # A DuplicateResult outlives the search job that produced it (SET NULL).
    subject = Subject(name="Math")
    doc = Document(subject=subject, filename="x.pdf", file_hash="h")
    chapter = Chapter(document=doc, subject=subject, title="Ch")
    topic = Topic(chapter=chapter, title="T")
    session.add(topic)
    session.flush()  # assign ids (subject_id is a NOT NULL FK on the job)
    job = QueueJob(topic=topic, subject_id=subject.id, stage=QueueStage.notes)
    session.add(job)
    session.commit()

    ex = _make_exercise(session)
    result = DuplicateResult(
        exercise=ex, problem_text="variant", queue_job_id=job.id
    )
    session.add(result)
    session.commit()
    assert result.queue_job_id == job.id

    session.delete(session.get(QueueJob, job.id))
    session.commit()
    session.expire(result)
    assert result.queue_job_id is None  # SET NULL kept the result


def test_foreign_key_enforced_on_exercise(session: Session) -> None:
    session.add(ExtractedExercise(session_id=999, raw_text="x", topic="t"))
    with pytest.raises(IntegrityError):
        session.commit()
