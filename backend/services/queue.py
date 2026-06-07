"""Persistent, budget-aware processing queue (reliability core).

Enqueues topics as per-stage ``QueueJob`` rows, orders work priority-first
(``exam_critical`` before ``medium``; ``skip`` never enqueued), respects per-topic
stage dependencies (formula → notes → assessment), processes a job through an
injected stage processor with atomic sub-stage commits, fails over / defers on
provider exhaustion, retries transient failures, and resumes from the DB after a
restart. The topic is the atomic unit; nothing here ever spans the whole document.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.models.enums import (
    DocumentMode,
    QueueLaneState,
    QueueStage,
    QueueState,
    TopicPriority,
    TopicStatus,
)
from backend.models.hierarchy import Chapter, Subject, Topic, utcnow
from backend.models.processing import ProviderState, QueueJob
from backend.services.providers.base import (
    AllProvidersExhausted,
    Provider,
    ProviderResult,
)

# A stage processor runs the stage's model call(s) (via the waterfall) and
# writes its domain rows (Note/MCQ/Formula/...) to the session WITHOUT
# committing — the queue commits everything atomically so a stage is never
# half-written. It returns the ProviderResult for stamping + cost, or raises.
StageProcessor = Callable[[QueueJob, Session], ProviderResult]


class JobOutcome(enum.StrEnum):
    """Result of processing one job — drives the batch loop."""

    done = "done"
    failed = "failed"  # terminal: exceeded max_attempts
    deferred_retry = "deferred_retry"  # transient failure, will retry later
    exhausted = "exhausted"  # all providers down — stop the batch, wait for wake-up


class SubjectLaneNotFound(Exception):
    """Raised when a lane operation targets a subject that doesn't exist."""

    def __init__(self, subject_id: int) -> None:
        super().__init__(f"subject {subject_id} not found")
        self.subject_id = subject_id


class ChapterLaneNotFound(Exception):
    """Raised when a chapter-lane operation targets a chapter that doesn't exist."""

    def __init__(self, chapter_id: int) -> None:
        super().__init__(f"chapter {chapter_id} not found")
        self.chapter_id = chapter_id


# A job goes to `failed` after this many attempts (then it poisons only itself;
# every other topic is unaffected).
MAX_ATTEMPTS = 3
# Default wait before retrying a transiently-failed job.
RETRY_DELAY = timedelta(minutes=1)
# Fallback defer when exhaustion reports no concrete reset time (avoid spinning).
DEFAULT_DEFER = timedelta(minutes=5)

# Stage execution order within a topic: formula registration first (it now only
# detects + registers equation regions — vision is deferred/lazy), then the
# consolidated generation stage (`notes`) which produces notes + assessment in a
# single call. The old separate `assessment` stage is retired (no longer enqueued).
STAGE_ORDER: tuple[QueueStage, ...] = (
    QueueStage.formula,
    QueueStage.notes,
)
# Rank EVERY known stage (including the retired `assessment`) by enum order so any
# pre-existing `assessment` job in a live DB still sorts/eligibility-checks without
# a KeyError.
STAGE_RANK = {stage: i for i, stage in enumerate(QueueStage)}

# exam_critical dispatched first so partial completion yields what matters most.
PRIORITY_RANK = {TopicPriority.exam_critical: 0, TopicPriority.medium: 1}

# Default stages enqueued per topic. Formula may be a no-op when a topic has no
# math; it stays in the set so ordering/eligibility are uniform.
DEFAULT_STAGES: tuple[QueueStage, ...] = STAGE_ORDER

# Stages enqueued per topic in exam mode: the consolidated generation stage only.
# The formula stage attaches LaTeX to a Note, and exam docs have no notes, so it
# is skipped entirely (no wasted vision/registration work). See build-log E3.
EXAM_STAGES: tuple[QueueStage, ...] = (QueueStage.notes,)

# Rough per-topic token cost (cost-strategy.md "token budgets per call"). Source
# input is now bounded (~generation.SOURCE_MAX_CHARS) and outputs are capped, so a
# topic's two text stages cost ~ notes (≤2k in + ≤2k out) + assessment (≤2k in +
# ≤2k out). Formula vision is variable/often zero and excluded. Used both for the
# pre-flight estimate and the per-document soft cap.
EST_TOKENS_PER_TOPIC = 8000
# A document may legitimately run somewhat over estimate; the auto budget pauses
# only a clear runaway (spend ≥ estimate × this factor).
DOC_BUDGET_OVERSPEND_FACTOR = 3


def estimate_topic_tokens(n_topics: int) -> int:
    """Pre-flight token estimate for ``n_topics`` non-skip topics."""
    return max(0, n_topics) * EST_TOKENS_PER_TOPIC


def document_token_usage(
    session: Session, document_id: int, *, override_budget: int = 0
) -> tuple[int, int]:
    """Return ``(tokens_spent, budget)`` for a document.

    ``budget`` is the flat ``override_budget`` when positive, else the automatic
    ceiling (estimate over the document's non-skip topics × the overspend factor).
    A non-positive result means "no enforced limit".
    """
    spent = session.scalar(
        select(func.coalesce(func.sum(QueueJob.tokens_used), 0))
        .select_from(QueueJob)
        .join(Topic, QueueJob.topic_id == Topic.id)
        .join(Chapter, Topic.chapter_id == Chapter.id)
        .where(Chapter.document_id == document_id)
    ) or 0
    if override_budget > 0:
        return spent, override_budget
    non_skip = session.scalar(
        select(func.count(Topic.id))
        .select_from(Topic)
        .join(Chapter, Topic.chapter_id == Chapter.id)
        .where(
            Chapter.document_id == document_id,
            Topic.priority != TopicPriority.skip,
        )
    ) or 0
    return spent, estimate_topic_tokens(non_skip) * DOC_BUDGET_OVERSPEND_FACTOR


# Lane contention rank: a foreground (actively-running) lane beats a background
# (overnight) lane when both want the same single-slot provider (point 8). A paused
# lane never competes (it is excluded entirely).
_LANE_RANK = {QueueLaneState.running: 0, QueueLaneState.overnight: 1}


@dataclass(frozen=True)
class _LaneCandidate:
    """A subject lane's highest-priority claimable job, ready for arbitration."""

    subject_id: int
    lane_rank: int  # 0 = foreground (running), 1 = background (overnight)
    job: QueueJob
    sort_key: tuple


@dataclass(frozen=True)
class DispatchClaim:
    """One arbitration result: a claimed job and the provider assigned to run it."""

    job_id: int
    provider: str


class QueueService:
    """Thin persistence-facing queue API over a SQLAlchemy session."""

    def __init__(
        self,
        session: Session,
        *,
        max_attempts: int = MAX_ATTEMPTS,
        clock: Callable[[], datetime] = utcnow,
        retry_delay: timedelta = RETRY_DELAY,
        default_defer: timedelta = DEFAULT_DEFER,
        per_doc_token_budget: int = 0,
    ) -> None:
        self.session = session
        self.max_attempts = max_attempts
        self.clock = clock
        self.retry_delay = retry_delay
        self.default_defer = default_defer
        # Per-document token ceiling: 0 = automatic (estimate × factor); a
        # positive value is a flat override. See ``document_token_usage``.
        self.per_doc_token_budget = per_doc_token_budget

    def enqueue_topic(
        self,
        topic: Topic,
        stages: tuple[QueueStage, ...] = DEFAULT_STAGES,
        *,
        commit: bool = True,
    ) -> list[QueueJob]:
        """Create pending jobs for a topic's stages (idempotent per stage).

        ``skip``-priority topics are never sent to a model, so none are created.
        ``commit=False`` lets a caller batch several topics into one transaction
        (e.g. structure confirmation enqueues a whole document atomically).
        """
        if topic.priority is TopicPriority.skip:
            return []

        # Query the DB for existing stages (not the cached relationship
        # collection, which can be stale within a session).
        existing = set(
            self.session.scalars(
                select(QueueJob.stage).where(QueueJob.topic_id == topic.id)
            ).all()
        )
        # Denormalized lane key — the topic's subject via its chapter. Set on
        # every created job so lane queries never re-join the hierarchy.
        subject_id = topic.chapter.subject_id
        created: list[QueueJob] = []
        for stage in stages:
            if stage in existing:
                continue
            job = QueueJob(topic_id=topic.id, subject_id=subject_id, stage=stage)
            self.session.add(job)
            created.append(job)
        if commit:
            self.session.commit()
        return created

    def pending_in_priority_order(self) -> list[QueueJob]:
        """Pending generation jobs, exam-critical-first then by position/stage.

        Excludes ``duplicate_search`` jobs — those are topic-less and drained by a
        separate search loop (``claim_next_search``), never the lane/topic path, so
        they must not reach ``_sort_key`` (which dereferences ``job.topic``).
        """
        jobs = self.session.scalars(
            select(QueueJob).where(
                QueueJob.state == QueueState.pending,
                QueueJob.stage != QueueStage.duplicate_search,
            )
        ).all()
        return sorted(jobs, key=self._sort_key)

    def has_pending_search(self) -> bool:
        """Cheap existence check: is any ``duplicate_search`` job pending and due?

        Lets the worker skip the settings/waterfall setup on idle ticks when the
        Stage-2 lane is empty (the common case) instead of loading settings every
        cycle. Mirrors ``claim_next_search``'s eligibility filter.
        """
        now = self.clock()
        return (
            self.session.scalar(
                select(QueueJob.id)
                .where(
                    QueueJob.state == QueueState.pending,
                    QueueJob.stage == QueueStage.duplicate_search,
                    or_(QueueJob.resume_after.is_(None), QueueJob.resume_after <= now),
                )
                .limit(1)
            )
            is not None
        )

    def claim_next_search(self) -> QueueJob | None:
        """Atomically claim the next due pending ``duplicate_search`` job.

        The Exercise Duplicator's Stage-2 lane, fully independent of the generation
        queue: oldest-first, honours ``resume_after``, no priority/lane arbitration
        and no stage prerequisites. Returns the claimed job (now ``running``) or None.
        """
        now = self.clock()
        job = self.session.scalars(
            select(QueueJob)
            .where(
                QueueJob.state == QueueState.pending,
                QueueJob.stage == QueueStage.duplicate_search,
                or_(QueueJob.resume_after.is_(None), QueueJob.resume_after <= now),
            )
            .order_by(QueueJob.created_at.asc(), QueueJob.id.asc())
        ).first()
        if job is None:
            return None
        job.state = QueueState.running
        self.session.commit()
        return job

    def claim_next(self) -> QueueJob | None:
        """Atomically move the next eligible pending job to ``running``.

        Eligible = highest priority, **due now** (``resume_after`` unset or in the
        past — a deferred job is never dispatched before its provider's reset),
        whose earlier-stage jobs for the same topic are all ``done``. Returns the
        claimed job, or None if nothing is ready.
        """
        now = self.clock()
        over_budget: dict[int, bool] = {}  # document_id → over its token budget
        paused_topics = self._paused_chapter_topic_ids()
        for job in self.pending_in_priority_order():
            if job.topic_id in paused_topics:
                continue  # the topic's chapter lane is paused — never dispatch it
            if job.resume_after is not None and job.resume_after > now:
                continue  # deferred until its reset/retry window
            if self._document_over_budget(job.topic_id, over_budget):
                continue  # document hit its token ceiling — pause, don't spend more
            if self._prerequisites_done(job):
                job.state = QueueState.running
                self._sync_topic_status(job.topic_id)
                self.session.commit()
                return job
        return None

    # -- lane-aware dispatch (Wave B) ----------------------------------------

    def claim_dispatch(
        self,
        providers: Sequence[Provider],
        *,
        blocked_providers: frozenset[str] = frozenset(),
    ) -> list[DispatchClaim]:
        """Arbitrate one dispatch cycle: claim ≤1 job per available provider.

        The cap is **one in-flight topic per provider** (point 7): a provider that
        already holds a running job, is disabled, has no headroom, or is temporarily
        blocked (e.g. a free-tier request-pacing gate) is skipped. Lanes compete for
        the remaining slots cheapest-first; when two lanes want the same provider the
        **foreground** (running) lane wins and the background (overnight) lane waits
        (point 8). Paused lanes never dispatch (point 9).

        Each claim atomically marks its job ``running`` and stamps the assigned
        provider, so both the in-flight set and a lane's active provider are
        derivable from the DB. Returns the claims for the caller to execute — each
        on a single-provider waterfall, so a job can't silently spill onto another
        provider's slot and break the per-provider cap.
        """
        now = self.clock()
        in_flight = set(
            self.session.scalars(
                select(QueueJob.assigned_provider).where(
                    QueueJob.state == QueueState.running,
                    QueueJob.assigned_provider.is_not(None),
                )
            ).all()
        )
        available: list[Provider] = []
        for provider in providers:  # cost order preserved
            if not provider.enabled:
                continue
            if provider.name in in_flight or provider.name in blocked_providers:
                continue
            probe = provider.budget_probe()
            if not probe.available or probe.headroom <= 0:
                continue
            available.append(provider)
        if not available:
            return []

        candidates = self._eligible_lane_candidates(now)
        if not candidates:
            return []

        claims: list[DispatchClaim] = []
        taken_subjects: set[int] = set()
        for provider in available:  # cheapest slot → highest-ranked waiting lane
            for candidate in candidates:
                if candidate.subject_id in taken_subjects:
                    continue
                job = candidate.job
                job.state = QueueState.running
                job.assigned_provider = provider.name
                self._sync_topic_status(job.topic_id)
                claims.append(DispatchClaim(job.id, provider.name))
                taken_subjects.add(candidate.subject_id)
                break
        if claims:
            self.session.commit()
        return claims

    def waiting_lanes(self, providers: Sequence[Provider]) -> dict[int, str]:
        """Lanes that have eligible work but lost provider contention this cycle.

        Returns ``{subject_id: provider_name}`` — the (cheapest in-flight) provider
        each waiting lane is blocked on, for the queue view's "waiting for <provider>".
        A lane is waiting when it's eligible but every provider it could use is
        already in-flight for another lane.
        """
        now = self.clock()
        running = dict(
            self.session.execute(
                select(QueueJob.assigned_provider, QueueJob.subject_id).where(
                    QueueJob.state == QueueState.running,
                    QueueJob.assigned_provider.is_not(None),
                )
            ).all()
        )
        busy_providers = set(running)
        if not busy_providers:
            return {}
        enabled_names = [p.name for p in providers if p.enabled]
        in_flight_subjects = set(running.values())
        waiting: dict[int, str] = {}
        for candidate in self._eligible_lane_candidates(now):
            if candidate.subject_id in in_flight_subjects:
                continue  # already running somewhere — not waiting
            blocker = next((n for n in enabled_names if n in busy_providers), None)
            if blocker is not None:
                waiting[candidate.subject_id] = blocker
        return waiting

    def set_lane_state(self, subject_id: int, state: QueueLaneState) -> None:
        """Set a subject lane's state, persisted so it survives restart (point 9).

        Pausing additionally rolls this lane's in-flight jobs cleanly back to
        ``pending`` (never half-written: ``process_job`` commits a stage atomically,
        so a running job wrote no domain rows). That frees a single-instance provider
        (e.g. Ollama) for a waiting lane — the manual hand-over mechanism.
        """
        subject = self.session.get(Subject, subject_id)
        if subject is None:
            raise SubjectLaneNotFound(subject_id)
        subject.queue_state = state
        if state is QueueLaneState.paused:
            running = self.session.scalars(
                select(QueueJob).where(
                    QueueJob.subject_id == subject_id,
                    QueueJob.state == QueueState.running,
                )
            ).all()
            for job in running:
                job.state = QueueState.pending
                job.assigned_provider = None
                self._sync_topic_status(job.topic_id)
        self.session.commit()

    def pause_lane(self, subject_id: int) -> None:
        self.set_lane_state(subject_id, QueueLaneState.paused)

    def resume_lane(self, subject_id: int) -> None:
        self.set_lane_state(subject_id, QueueLaneState.running)

    def set_overnight(self, subject_id: int, enabled: bool) -> None:
        self.set_lane_state(
            subject_id,
            QueueLaneState.overnight if enabled else QueueLaneState.running,
        )

    # -- per-chapter lanes (Chapter Lanes) -----------------------------------

    def set_chapter_state(self, chapter_id: int, state: QueueLaneState) -> None:
        """Set a chapter lane's state, persisted on the ``Chapter`` row.

        Pausing rolls this chapter's in-flight jobs cleanly back to ``pending``
        (same safety as ``pause_lane`` — ``process_job`` commits atomically, so a
        running job wrote no domain rows). Un-pausing (``running``/``overnight``)
        enqueues jobs for any non-skip topic in the chapter that has none yet, so a
        chapter confirmed paused (no jobs created) starts processing on resume.
        """
        chapter = self.session.get(Chapter, chapter_id)
        if chapter is None:
            raise ChapterLaneNotFound(chapter_id)
        chapter.queue_state = state
        if state is QueueLaneState.paused:
            self._rollback_chapter_inflight(chapter_id)
        else:
            self._enqueue_missing_chapter_topics(chapter)
        self.session.commit()

    def pause_chapter(self, chapter_id: int) -> None:
        self.set_chapter_state(chapter_id, QueueLaneState.paused)

    def resume_chapter(self, chapter_id: int) -> None:
        self.set_chapter_state(chapter_id, QueueLaneState.running)

    def _rollback_chapter_inflight(self, chapter_id: int) -> None:
        running = self.session.scalars(
            select(QueueJob)
            .join(Topic, QueueJob.topic_id == Topic.id)
            .where(
                Topic.chapter_id == chapter_id,
                QueueJob.state == QueueState.running,
            )
        ).all()
        for job in running:
            job.state = QueueState.pending
            job.assigned_provider = None
            self._sync_topic_status(job.topic_id)

    def _enqueue_missing_chapter_topics(self, chapter: Chapter) -> None:
        stages = self._stages_for_chapter(chapter)
        topics = self.session.scalars(
            select(Topic).where(Topic.chapter_id == chapter.id)
        ).all()
        for topic in topics:
            if topic.priority is TopicPriority.skip:
                continue
            has_jobs = self.session.scalar(
                select(func.count())
                .select_from(QueueJob)
                .where(QueueJob.topic_id == topic.id)
            )
            if not has_jobs:
                self.enqueue_topic(topic, stages, commit=False)

    @staticmethod
    def _stages_for_chapter(chapter: Chapter) -> tuple[QueueStage, ...]:
        """Generation stages for a chapter's topics, per the document.

        The formula stage crops equations from a PDF page; exam docs (no notes) and
        audio docs (transcript only, no PDF) skip it and run generation only.
        """
        document = chapter.document
        if document is not None and (
            document.mode is DocumentMode.exam or document.source_type == "audio"
        ):
            return EXAM_STAGES
        return DEFAULT_STAGES

    def _paused_chapter_topic_ids(self) -> set[int]:
        """Topic ids whose chapter lane is paused — their jobs are never claimed."""
        return set(
            self.session.scalars(
                select(Topic.id)
                .join(Chapter, Topic.chapter_id == Chapter.id)
                .where(Chapter.queue_state == QueueLaneState.paused)
            ).all()
        )

    def _eligible_lane_candidates(self, now: datetime) -> list[_LaneCandidate]:
        """Each non-paused lane's highest-priority *claimable* job, ranked.

        Walks pending jobs in global priority order and takes the first eligible one
        per subject (due now, prerequisites done, document under budget). Lanes are
        then ordered foreground-first, then by that job's priority — the order
        provider slots are handed out in.
        """
        lane_states = self._lane_states()
        paused_topics = self._paused_chapter_topic_ids()
        over_budget: dict[int, bool] = {}
        candidates: list[_LaneCandidate] = []
        seen: set[int] = set()
        for job in self.pending_in_priority_order():
            subject_id = job.subject_id
            if subject_id in seen:
                continue
            state = lane_states.get(subject_id, QueueLaneState.running)
            if state is QueueLaneState.paused:
                seen.add(subject_id)  # lane hard-stopped — never dispatch it
                continue
            if job.topic_id in paused_topics:
                # Chapter lane paused — skip this job but NOT the whole subject lane:
                # another (running) chapter in the same subject may still dispatch.
                continue
            if job.resume_after is not None and job.resume_after > now:
                continue  # deferred; a later job in this lane may still be eligible
            if self._document_over_budget(job.topic_id, over_budget):
                continue
            if not self._prerequisites_done(job):
                continue
            candidates.append(
                _LaneCandidate(
                    subject_id=subject_id,
                    lane_rank=_LANE_RANK.get(state, 0),
                    job=job,
                    sort_key=self._sort_key(job),
                )
            )
            seen.add(subject_id)
        candidates.sort(key=lambda c: (c.lane_rank, c.sort_key, c.subject_id))
        return candidates

    def _lane_states(self) -> dict[int, QueueLaneState]:
        return dict(
            self.session.execute(select(Subject.id, Subject.queue_state)).all()
        )

    def process_job(self, job: QueueJob, processor: StageProcessor) -> JobOutcome:
        """Run one claimed job's stage and commit the result atomically.

        Success: the processor's domain rows + the job's `done`/stamping + the
        provider's cost are committed together — a sub-stage commit that never
        leaves a topic half-written. Budget exhaustion rolls back any partial
        write and defers the job (attempts unchanged) until its reset. Any other
        failure rolls back, increments attempts, defers a retry, and goes to
        `failed` after `max_attempts`.
        """
        now = self.clock()
        try:
            result = processor(job, self.session)
        except AllProvidersExhausted as exc:
            # Not a job failure — a budget pause. Defer until the reset (or a
            # default if none is known, to avoid spinning). Attempts unchanged.
            # Record *why* so a perpetually-throttled provider (e.g. a free tier
            # at limit:0 answering 429) isn't an invisible, forever-deferred stall
            # — the queue view surfaces this as `paused_reason`.
            self.session.rollback()
            job = self.session.get(QueueJob, job.id)
            job.state = QueueState.pending
            job.resume_after = exc.retry_at or (now + self.default_defer)
            job.last_error = exc.reason
            self.session.commit()
            return JobOutcome.exhausted
        except Exception as exc:  # noqa: BLE001 - a failed topic must poison only itself
            self.session.rollback()
            job = self.session.get(QueueJob, job.id)
            job.attempts += 1
            job.last_error = str(exc)
            if job.attempts >= self.max_attempts:
                job.state = QueueState.failed
                job.resume_after = None
                outcome = JobOutcome.failed
            else:
                # Defer the retry so it isn't re-claimed immediately this batch.
                job.state = QueueState.pending
                job.resume_after = now + self.retry_delay
                outcome = JobOutcome.deferred_retry
            self._sync_topic_status(job.topic_id)
            self.session.commit()
            return outcome

        job.assigned_provider = result.provider
        job.last_error = None
        job.resume_after = None
        job.state = QueueState.done
        job.tokens_used = result.input_tokens + result.output_tokens
        self._record_provider_usage(result)
        self._sync_topic_status(job.topic_id)
        self.session.commit()
        return JobOutcome.done

    def recover_orphaned_jobs(self) -> int:
        """Reset jobs stuck in `running` (interrupted mid-process) to `pending`.

        Called on startup. Safe because `process_job` commits a stage
        atomically: an interrupted job never wrote its domain rows, so
        re-running it loses nothing and leaves nothing half-written.
        """
        orphaned = self.session.scalars(
            select(QueueJob).where(QueueJob.state == QueueState.running)
        ).all()
        for job in orphaned:
            job.state = QueueState.pending
        self.session.commit()
        return len(orphaned)

    def release_running_job(self, job_id: int) -> bool:
        """Reset a claimed-but-unprocessed job back to pending (worker safety net).

        With the lane model the claim (mark ``running``) and the processing happen
        in separate steps/threads. If a dispatch worker dies *after* claiming but
        *before* ``process_job`` commits an outcome, the job would otherwise sit in
        ``running`` until the next restart's orphan recovery. This releases it
        immediately so the slot frees up. No-op unless the job is still running
        (a completed job has already moved past ``running``).
        """
        job = self.session.get(QueueJob, job_id)
        if job is None or job.state is not QueueState.running:
            return False
        job.state = QueueState.pending
        job.assigned_provider = None
        self._sync_topic_status(job.topic_id)
        self.session.commit()
        return True

    def retry_topic(self, topic_id: int) -> int:
        """Requeue a topic's terminally-failed jobs (the retry UI action).

        Resets each ``failed`` job to ``pending`` with a fresh attempt budget and
        cleared error/defer, then re-derives the topic status. Returns how many
        jobs were requeued (0 if the topic had none failed).
        """
        failed = self.session.scalars(
            select(QueueJob).where(
                QueueJob.topic_id == topic_id,
                QueueJob.state == QueueState.failed,
            )
        ).all()
        for job in failed:
            job.state = QueueState.pending
            job.attempts = 0
            job.last_error = None
            job.resume_after = None
        if failed:
            self._sync_topic_status(topic_id)
        self.session.commit()
        return len(failed)

    def earliest_resume_after(self) -> datetime | None:
        """The single wake-up time: earliest `resume_after` among deferred jobs."""
        return self.session.scalars(
            select(QueueJob.resume_after)
            .where(
                QueueJob.state == QueueState.pending,
                QueueJob.resume_after.is_not(None),
            )
            .order_by(QueueJob.resume_after.asc())
        ).first()

    def run_batch(
        self,
        processor: StageProcessor,
        *,
        max_jobs: int,
        throttle: Callable[[QueueJob, "JobOutcome"], None] | None = None,
    ) -> int:
        """Claim and process due jobs until exhaustion, max_jobs, or none left.

        Returns the number of jobs processed (done/failed/deferred-retry). Stops
        immediately on provider exhaustion — every job would also be exhausted —
        and the caller then sleeps until ``earliest_resume_after``. Transiently
        failed jobs are deferred (not re-claimed this batch), so the loop moves on
        to other topics and never spins.

        ``throttle`` is an optional ``(job, outcome) -> None`` hook invoked after
        each processed job (used by the background worker to space out free-tier
        model calls and stay under the rolling per-minute request ceiling).
        """
        processed = 0
        while processed < max_jobs:
            job = self.claim_next()
            if job is None:
                break
            outcome = self.process_job(job, processor)
            if outcome is JobOutcome.exhausted:
                break
            processed += 1
            if throttle is not None:
                throttle(job, outcome)
        return processed

    @staticmethod
    def budget_count(headroom: int, est_cost_per_topic: int) -> int:
        """How many jobs current headroom allows: floor(headroom / est).

        A non-positive estimate means "unknown" → dispatch nothing (the caller
        seeds the per-document estimate from the first processed topics).
        """
        if est_cost_per_topic <= 0:
            return 0
        return max(0, headroom // est_cost_per_topic)

    # -- internals -----------------------------------------------------------

    def _sort_key(self, job: QueueJob) -> tuple[int, int, int, int]:
        topic = job.topic
        chapter = topic.chapter
        return (
            PRIORITY_RANK.get(topic.priority, 99),
            chapter.order_index,
            topic.order_index,
            STAGE_RANK[job.stage],
        )

    def _record_provider_usage(self, result: ProviderResult) -> None:
        """Accumulate spend/usage on the serving provider's ProviderState row."""
        state = self.session.scalars(
            select(ProviderState).where(ProviderState.provider == result.provider)
        ).one_or_none()
        if state is None:
            state = ProviderState(provider=result.provider)
            self.session.add(state)
        # Column defaults apply at flush, so a freshly-added row reads None here.
        state.total_cost = (state.total_cost or 0.0) + result.cost
        state.total_tokens = (
            (state.total_tokens or 0) + result.input_tokens + result.output_tokens
        )

    def _document_over_budget(self, topic_id: int, cache: dict[int, bool]) -> bool:
        """Whether the topic's document has spent ≥ its token budget (cached).

        Pausing a runaway document is defense-in-depth (cost-strategy.md): its
        pending jobs simply aren't claimed — they stay ``pending`` (no defer) so a
        raised budget makes them claimable again on the next drain. A document with
        no budget (auto ceiling 0, i.e. no topics) is never blocked.
        """
        document_id = self.session.scalar(
            select(Chapter.document_id)
            .select_from(Topic)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(Topic.id == topic_id)
        )
        if document_id is None:
            return False
        if document_id not in cache:
            spent, budget = document_token_usage(
                self.session, document_id, override_budget=self.per_doc_token_budget
            )
            cache[document_id] = budget > 0 and spent >= budget
        return cache[document_id]

    def _prerequisites_done(self, job: QueueJob) -> bool:
        rank = STAGE_RANK[job.stage]
        siblings = self.session.scalars(
            select(QueueJob).where(QueueJob.topic_id == job.topic_id)
        ).all()
        return all(
            sibling.state == QueueState.done
            for sibling in siblings
            if STAGE_RANK[sibling.stage] < rank
        )

    def _sync_topic_status(self, topic_id: int | None) -> None:
        """Derive the topic's status from its jobs (the queue owns this lifecycle).

        error if any stage failed terminally · ready once every stage is done ·
        processing while any stage is running or already done (partial progress) ·
        queued otherwise. Topics with no jobs (``skip``) are left untouched.
        Mutates in the caller's open transaction — never commits on its own.

        ``topic_id`` is None for ``duplicate_search`` jobs (no topic lifecycle) —
        a no-op then.
        """
        if topic_id is None:
            return
        # Flush so the just-set job states are visible to this SELECT even when
        # the session has autoflush off (production SessionLocal does).
        self.session.flush()
        states = self.session.scalars(
            select(QueueJob.state).where(QueueJob.topic_id == topic_id)
        ).all()
        if not states:
            return
        topic = self.session.get(Topic, topic_id)
        if topic is None:
            return
        if any(state == QueueState.failed for state in states):
            topic.status = TopicStatus.error
        elif all(state == QueueState.done for state in states):
            topic.status = TopicStatus.ready
        elif any(state in (QueueState.done, QueueState.running) for state in states):
            topic.status = TopicStatus.processing
        else:
            topic.status = TopicStatus.queued
