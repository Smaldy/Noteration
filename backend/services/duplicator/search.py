"""Stage 2 — Duplicate (variant) search, drained on the background queue.

A ``duplicate_search`` ``QueueJob`` carries an ``exercise_id`` (no topic). Its
processor loads the exercise + its session's year level, grounds the prompt with
up to five calibration samples for that topic+year, asks the model for 3–5 real
university-level variant problems, and writes ``DuplicateResult`` rows. The
processor has the same ``StageProcessor`` shape as the generation processors so
the queue owns the atomic commit, failover, retry, and resume.

These jobs are drained by ``drain_search_once`` — a dedicated loop independent of
the topic/lane generation path (``QueueService.claim_next_search``), so the
reliability core's hot path never sees a topic-less job.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from backend.models.duplicator import (
    CalibrationSample,
    DuplicateResult,
    ExerciseSession,
    ExtractedExercise,
)
from backend.models.enums import ExerciseStatus
from backend.models.processing import QueueJob
from backend.services.duplicator.calibration import recent_samples
from backend.services.duplicator.extraction import _extract_json_array
from backend.services.pipeline.formula import NO_OP_PROVIDER
from backend.services.providers.base import ProviderResult
from backend.services.providers.waterfall import Waterfall
from backend.services.queue import JobOutcome, QueueService

logger = logging.getLogger(__name__)

# 3–5 variant problems (with optional viz) fit comfortably here.
SEARCH_MAX_TOKENS = 3072

SampleLoader = Callable[[Session, str, int], "list[CalibrationSample]"]
StageProcessor = Callable[[QueueJob, Session], ProviderResult]
Throttle = Callable[[QueueJob, JobOutcome], None]


@dataclass
class ParsedVariant:
    problem_text: str
    source_url: str | None = None
    difficulty_score: float | None = None
    viz: dict[str, Any] | None = None


def build_search_prompt(
    exercise: ExtractedExercise,
    year_level: int,
    calibration_samples: list[CalibrationSample],
) -> str:
    """Prompt the model for real university-level variants of one exercise."""
    if calibration_samples:
        examples = "\n".join(
            f"- {s.source_text.strip()}" for s in calibration_samples
        )
        examples_block = (
            "\n# Calibration examples (real problems at this topic+year — match "
            f"their level and style)\n{examples}\n"
        )
    else:
        examples_block = ""  # cold start: no fabricated examples

    subtopic_line = f" / {exercise.subtopic}" if exercise.subtopic else ""
    return (
        "You are an expert university mathematics/physics problem setter. Given an "
        "original exercise, produce real university-level VARIANT problems that "
        "test the same concepts at the same depth.\n\n"
        f"These variants are for a university mathematics/physics major, year "
        f"{year_level} (1 = first year … 5 = final year).\n"
        f"Topic: {exercise.topic}{subtopic_line}\n\n"
        "# Original exercise\n"
        f"{exercise.raw_text.strip()}\n"
        f"{examples_block}\n"
        "Respond with ONLY a JSON array of 3–5 objects — no prose, no code fences:\n"
        "[{\n"
        '  "problem_text": str,            // the full variant problem statement\n'
        '  "source_url": str | null,       // a known source if you have one\n'
        '  "difficulty_score": float,      // 0.0 (easy) … 1.0 (hard)\n'
        '  "viz": null | {"type": "...", "expression": "...", "domain": [a, b], '
        '"params": {}}\n'
        "}]\n\n"
        "Rules:\n"
        "- Problems MUST require proof, structural reasoning, or multi-step "
        "derivation. Do NOT generate high-school-level computations.\n"
        "- Prefer problems from known university sources (MIT OCW, university exam "
        "archives); set `source_url` when you genuinely know it, else null.\n"
        "- Include a `viz` block ONLY when a visualization would directly aid "
        "solving the problem; otherwise null. Valid `viz.type`: mafs_function, "
        "mafs_parametric, plotly_3d, plotly_complex, matter_simulation, "
        "force_diagram.\n"
    )


def parse_variants(text: str) -> list[ParsedVariant]:
    """Parse the variants array, skipping malformed items (tolerant)."""
    try:
        data = json.loads(_extract_json_array(text))
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning("duplicator: unparseable search response: %s", exc)
        return []
    if not isinstance(data, list):
        return []

    variants: list[ParsedVariant] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        problem_text = item.get("problem_text")
        if not isinstance(problem_text, str) or not problem_text.strip():
            continue
        source_url = item.get("source_url")
        source_url = source_url.strip() if isinstance(source_url, str) and source_url.strip() else None
        score = item.get("difficulty_score")
        score = (
            float(min(1.0, max(0.0, score)))
            if isinstance(score, (int, float)) and not isinstance(score, bool)
            else None
        )
        viz = item.get("viz")
        viz = viz if isinstance(viz, dict) else None
        variants.append(
            ParsedVariant(
                problem_text=problem_text.strip(),
                source_url=source_url,
                difficulty_score=score,
                viz=viz,
            )
        )
    return variants


def make_duplicate_search_processor(
    waterfall: Waterfall, *, sample_loader: SampleLoader = recent_samples
) -> StageProcessor:
    """Build the ``StageProcessor`` for a ``duplicate_search`` job.

    Loads the exercise + its session's year level, grounds the prompt with recent
    calibration samples, calls the model, parses tolerantly, writes
    ``DuplicateResult`` rows (uncommitted — the queue commits), and flips the
    exercise to ``done``. A vanished exercise (deleted mid-flight) is a no-op.
    """

    def process(job: QueueJob, session: Session) -> ProviderResult:
        exercise = (
            session.get(ExtractedExercise, job.exercise_id)
            if job.exercise_id is not None
            else None
        )
        if exercise is None:
            return ProviderResult(text="", provider=NO_OP_PROVIDER)

        exercise_session = session.get(ExerciseSession, exercise.session_id)
        year_level = exercise_session.year_level if exercise_session else 1
        samples = sample_loader(session, exercise.topic, year_level)

        prompt = build_search_prompt(exercise, year_level, samples)
        result = waterfall.generate(prompt, max_tokens=SEARCH_MAX_TOKENS)

        for variant in parse_variants(result.text):
            session.add(
                DuplicateResult(
                    exercise_id=exercise.id,
                    problem_text=variant.problem_text,
                    source_url=variant.source_url,
                    difficulty_score=variant.difficulty_score,
                    viz=variant.viz,
                    queue_job_id=job.id,
                )
            )
        exercise.status = ExerciseStatus.done
        return result

    return process


def drain_search_once(
    session: Session,
    queue: QueueService,
    waterfall: Waterfall,
    *,
    max_jobs: int,
    throttle: Throttle | None = None,
) -> int:
    """Claim and process due ``duplicate_search`` jobs; return how many ran.

    Independent of the generation drain. Marks an exercise ``searching`` on claim
    and ``error`` on terminal job failure; the processor marks ``done`` on success.
    Stops on provider exhaustion (the job is deferred, the exercise stays
    ``searching`` to retry later).
    """
    processed = 0
    processor = make_duplicate_search_processor(waterfall)
    while processed < max_jobs:
        job = queue.claim_next_search()
        if job is None:
            break
        exercise = (
            session.get(ExtractedExercise, job.exercise_id)
            if job.exercise_id is not None
            else None
        )
        if exercise is not None and exercise.status is ExerciseStatus.pending:
            exercise.status = ExerciseStatus.searching
            session.commit()

        outcome = queue.process_job(job, processor)
        if outcome is JobOutcome.exhausted:
            break
        if outcome is JobOutcome.failed and exercise is not None:
            exercise.status = ExerciseStatus.error
            session.commit()
        processed += 1
        if throttle is not None:
            throttle(job, outcome)
    return processed
