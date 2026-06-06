"""Exercise Duplicator Stage 2 — duplicate_search queue lane (Wave ED-3)."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Chapter, Document, Subject, Topic
from backend.models.duplicator import (
    CalibrationSample,
    DuplicateResult,
    ExerciseSession,
    ExtractedExercise,
)
from backend.models.enums import (
    ExerciseStatus,
    QueueLaneState,
    QueueStage,
    QueueState,
)
from backend.models.processing import QueueJob
from backend.services.duplicator import sessions as sessionsvc
from backend.services.duplicator.calibration import recent_samples
from backend.services.duplicator.search import (
    build_search_prompt,
    drain_search_once,
    make_duplicate_search_processor,
    parse_variants,
)
from backend.services.providers.base import ProviderLimitError
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall
from backend.services.queue import QueueService


def _variants_json(*texts: str) -> str:
    return json.dumps(
        [{"problem_text": t, "difficulty_score": 0.7} for t in texts]
    )


def _make_search_job(
    session: Session,
    *,
    year_level: int = 3,
    topic: str = "complex_analysis.residues",
    raw: str = "Compute the residue of 1/(z^2+1) at z=i.",
) -> tuple[ExtractedExercise, QueueJob]:
    es = ExerciseSession(document_hash="h", year_level=year_level)
    ex = ExtractedExercise(session=es, order_index=0, raw_text=raw, topic=topic)
    session.add(ex)
    session.flush()
    job = QueueJob(stage=QueueStage.duplicate_search, exercise_id=ex.id)
    session.add(job)
    session.commit()
    return ex, job


def _wf(provider: MockProvider) -> Waterfall:
    return Waterfall([provider])


# --- processor + drain ------------------------------------------------------


def test_processor_writes_results_and_marks_done(session: Session) -> None:
    ex, job = _make_search_job(session)
    wf = _wf(MockProvider("mock", text=_variants_json("Variant A", "Variant B")))

    n = drain_search_once(session, QueueService(session), wf, max_jobs=10)

    assert n == 1
    session.refresh(ex)
    assert ex.status is ExerciseStatus.done
    results = session.scalars(select(DuplicateResult)).all()
    assert {r.problem_text for r in results} == {"Variant A", "Variant B"}
    assert all(r.queue_job_id == job.id for r in results)
    assert all(r.difficulty_score == 0.7 for r in results)
    session.refresh(job)
    assert job.state is QueueState.done


def test_processor_tolerates_malformed(session: Session) -> None:
    ex, _ = _make_search_job(session)
    wf = _wf(MockProvider("mock", text="the model rambled with no json"))

    drain_search_once(session, QueueService(session), wf, max_jobs=10)

    session.refresh(ex)
    assert ex.status is ExerciseStatus.done  # search ran; just yielded nothing
    assert session.scalars(select(DuplicateResult)).all() == []


def test_cold_start_omits_calibration_section(session: Session) -> None:
    ex, _ = _make_search_job(session)
    prompt = build_search_prompt(ex, 3, [])
    assert "Calibration examples" not in prompt
    assert ex.raw_text in prompt
    assert ex.topic in prompt
    # And the drain works end-to-end with no samples present.
    wf = _wf(MockProvider("mock", text=_variants_json("Cold variant")))
    drain_search_once(session, QueueService(session), wf, max_jobs=10)
    session.refresh(ex)
    assert ex.status is ExerciseStatus.done


def test_calibration_samples_feed_prompt(session: Session) -> None:
    ex, _ = _make_search_job(session, topic="algebra.groups", year_level=2)
    session.add(
        CalibrationSample(
            topic="algebra.groups",
            year_level=2,
            source_text="Show the center of a p-group is nontrivial.",
        )
    )
    # A non-matching sample (different year) must be excluded.
    session.add(
        CalibrationSample(
            topic="algebra.groups", year_level=5, source_text="other-year sample"
        )
    )
    session.commit()

    samples = recent_samples(session, "algebra.groups", 2)
    assert [s.source_text for s in samples] == [
        "Show the center of a p-group is nontrivial."
    ]
    prompt = build_search_prompt(ex, 2, samples)
    assert "Calibration examples" in prompt
    assert "center of a p-group" in prompt


def test_exhaustion_keeps_exercise_searching(session: Session) -> None:
    ex, job = _make_search_job(session)
    # An unavailable provider → the waterfall raises AllProvidersExhausted.
    wf = _wf(MockProvider("mock", available=False, headroom=0))

    n = drain_search_once(session, QueueService(session), wf, max_jobs=10)

    assert n == 0  # stopped on exhaustion
    session.refresh(ex)
    assert ex.status is ExerciseStatus.searching  # claimed, deferred, will retry
    session.refresh(job)
    assert job.state is QueueState.pending
    assert job.resume_after is not None


def test_terminal_failure_marks_exercise_error(session: Session) -> None:
    ex, job = _make_search_job(session)
    wf = _wf(MockProvider("mock", raises=ValueError("boom")))

    drain_search_once(session, QueueService(session, max_attempts=1), wf, max_jobs=10)

    session.refresh(ex)
    assert ex.status is ExerciseStatus.error
    session.refresh(job)
    assert job.state is QueueState.failed


def test_missing_exercise_is_noop(session: Session) -> None:
    # Defensive: a search job with no exercise reference completes as a no-op
    # (the FK CASCADE means a real job always has an exercise, so exercise_id=None
    # is the only way to reach this branch).
    job = QueueJob(stage=QueueStage.duplicate_search, exercise_id=None)
    session.add(job)
    session.commit()

    wf = _wf(MockProvider("mock", text=_variants_json("X")))
    drain_search_once(session, QueueService(session), wf, max_jobs=10)
    session.refresh(job)
    assert job.state is QueueState.done
    assert session.scalars(select(DuplicateResult)).all() == []


# --- isolation from the generation queue ------------------------------------


def test_search_jobs_excluded_from_generation_path(session: Session) -> None:
    subject = Subject(name="Math")
    doc = Document(subject=subject, filename="x.pdf", file_hash="h")
    chapter = Chapter(
        document=doc, subject=subject, title="Ch", queue_state=QueueLaneState.running
    )
    topic = Topic(chapter=chapter, title="T")
    session.add(topic)
    session.flush()
    gen_job = QueueJob(
        topic_id=topic.id, subject_id=subject.id, stage=QueueStage.notes
    )
    session.add(gen_job)
    _, search_job = _make_search_job(session)
    session.commit()

    q = QueueService(session)
    pending_ids = {j.id for j in q.pending_in_priority_order()}
    assert gen_job.id in pending_ids
    assert search_job.id not in pending_ids  # never enters the lane/topic path

    # claim_next (generation) returns the topic job, never the search job.
    claimed = q.claim_next()
    assert claimed is not None and claimed.id == gen_job.id


def test_cascade_delete_session_removes_search_job(session: Session) -> None:
    ex, job = _make_search_job(session)
    es_id = ex.session_id
    session.delete(session.get(ExerciseSession, es_id))
    session.commit()
    # The exercise CASCADE removes its duplicate_search job (exercise_id FK).
    assert session.scalars(select(QueueJob)).all() == []


def test_parse_variants_clamps_score_and_skips_bad() -> None:
    text = json.dumps(
        [
            {"problem_text": "ok", "difficulty_score": 1.7},  # clamped to 1.0
            {"difficulty_score": 0.5},  # no problem_text → skip
            42,  # not an object → skip
            {"problem_text": "  ", "difficulty_score": 0.1},  # blank → skip
        ]
    )
    variants = parse_variants(text)
    assert len(variants) == 1
    assert variants[0].problem_text == "ok"
    assert variants[0].difficulty_score == 1.0


def test_end_to_end_create_session_then_search(session: Session, tmp_path) -> None:
    from backend.services.pipeline.ingestion import IngestionResult

    exercises_json = json.dumps(
        [
            {"raw_text": "Prove IVT.", "topic": "analysis.ivt"},
            {"raw_text": "Find d/dx x^3.", "topic": "calculus.derivatives"},
        ]
    )
    vision_wf = _wf(MockProvider("vis", supports_vision=True, text=exercises_json))

    def _fake_ingest(pdf_path):
        return IngestionResult(
            file_hash="hash1",
            markdown="",
            markdown_path=None,
            page_image_paths=[],
            page_count=1,
            is_scanned=False,
            from_cache=False,
        )

    created = sessionsvc.create_session(
        session,
        data=b"%PDF-1.4\nx",
        filename="ex.pdf",
        year_level=2,
        subject_hint=None,
        waterfall=vision_wf,
        ingest_fn=_fake_ingest,
        uploads_dir=tmp_path / "uploads",
        load_pages=lambda h: [b"png"],
    )

    # Two exercises → two pending duplicate_search jobs enqueued in the same txn.
    search_jobs = session.scalars(
        select(QueueJob).where(QueueJob.stage == QueueStage.duplicate_search)
    ).all()
    assert len(search_jobs) == 2
    assert all(j.state is QueueState.pending for j in search_jobs)
    assert {j.exercise_id for j in search_jobs} == {e.id for e in created.exercises}

    # Drain Stage 2: each exercise gets variants and flips to done.
    search_wf = _wf(MockProvider("gen", text=_variants_json("V1", "V2")))
    n = drain_search_once(session, QueueService(session), search_wf, max_jobs=10)

    assert n == 2
    refetched = sessionsvc.get_exercise_session(session, created.id)
    assert all(e.status is ExerciseStatus.done for e in refetched.exercises)
    assert all(len(e.results) == 2 for e in refetched.exercises)


def test_processor_via_queue_process_job(session: Session) -> None:
    # Exercise the real QueueService.process_job path (atomic commit + stamping).
    ex, job = _make_search_job(session)
    q = QueueService(session)
    claimed = q.claim_next_search()
    assert claimed is not None and claimed.id == job.id
    processor = make_duplicate_search_processor(
        _wf(MockProvider("mock_prov", text=_variants_json("V1")))
    )
    outcome = q.process_job(claimed, processor)
    assert outcome.value == "done"
    session.refresh(job)
    assert job.assigned_provider == "mock_prov"
    assert session.scalars(select(DuplicateResult)).one().problem_text == "V1"
