"""AI study planner — distribute a subject's topics across a study calendar.

A user-triggered, synchronous single model call (modelled on
``topics.generate_more`` / formula transcription — it does NOT go through the
background generation queue). Given a subject, its non-skip topics (with
priorities), today, and a target end date (the exam date when set, else a short
default horizon), the model returns a day-by-day plan: which topic to study on
which date, with a short rationale note. We validate the plan against the
subject's real topics + the allowed date window, then materialise
``ScheduleEntry`` rows with ``source=ai`` (preserved across SM-2 rebuilds).

Re-planning a subject replaces only its previous ``ai`` entries — the user's own
``manual`` events and the SM-2 calendar are left untouched.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models import Chapter, ScheduleEntry, Subject, Topic
from backend.models.enums import ScheduleSource, TopicPriority
from backend.services.pipeline.generation import _extract_json_object
from backend.services.providers.factory import build_waterfall_from_settings
from backend.services.providers.waterfall import Waterfall
from backend.services.scheduler import REVISION_BUFFER_DAYS
from backend.services.settings import get_settings

# Output cap — a plan is a compact list of {topic_id, date, note}; 2k tokens
# comfortably covers a multi-week plan without risking a runaway.
PLAN_MAX_TOKENS = 2048
# When a subject has no exam date, plan over a sensible near-term horizon.
DEFAULT_PLAN_HORIZON_DAYS = 14

PLAN_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "sessions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "topic_id": {"type": "integer"},
                    "date": {"type": "string"},  # YYYY-MM-DD
                    "note": {"type": "string"},
                },
                "required": ["topic_id", "date"],
            },
        }
    },
    "required": ["sessions"],
}


class SubjectNotFoundError(LookupError):
    """The subject to plan does not exist."""


class NoTopicsToPlanError(Exception):
    """The subject has no studyable (non-skip) topics to schedule."""


class PlanParseError(Exception):
    """The model's plan output was not usable JSON."""


@dataclass
class ParsedSession:
    topic_id: int
    on_date: date
    note: str


def _plan_window(subject: Subject, *, today: date) -> tuple[date, date]:
    """The first and last day a session may be scheduled on.

    Ends on the exam date (minus the revision buffer, so the last days stay free
    for review) when there's a future exam; otherwise a short default horizon.
    """
    if subject.exam_date is not None and subject.exam_date > today:
        end = subject.exam_date - timedelta(days=REVISION_BUFFER_DAYS)
        # Never collapse the window to before today for a very near exam.
        return today, max(end, today)
    return today, today + timedelta(days=DEFAULT_PLAN_HORIZON_DAYS)


def _subject_topics(
    session: Session, subject_id: int, *, include_studied: bool = False
) -> list[Topic]:
    """The subject's studyable topics (non-``skip``), ordered for planning.

    ``studied`` topics are excluded by default — the user has marked them done,
    so the plan focuses on what's left."""
    stmt = (
        select(Topic)
        .join(Chapter, Topic.chapter_id == Chapter.id)
        .where(
            Chapter.subject_id == subject_id,
            Topic.priority != TopicPriority.skip,
        )
        .order_by(Chapter.order_index, Chapter.id, Topic.order_index, Topic.id)
    )
    if not include_studied:
        stmt = stmt.where(Topic.studied.is_(False))
    return list(session.scalars(stmt).all())


def _apply_studied(session: Session, subject_id: int, studied_ids: set[int]) -> None:
    """Set ``Topic.studied`` for the subject's topics to match the user's checks.

    The plan dialog shows the subject's topics pre-checked from their current
    ``studied`` flag; on generate we persist exactly that set (checked → studied),
    so checking a topic both records it and removes it from the plan.
    """
    for topic in session.scalars(
        select(Topic)
        .join(Chapter, Topic.chapter_id == Chapter.id)
        .where(Chapter.subject_id == subject_id)
    ):
        topic.studied = topic.id in studied_ids


def build_plan_prompt(
    subject_name: str,
    topics: list[Topic],
    *,
    today: date,
    start: date,
    end: date,
    exam_date: date | None = None,
) -> str:
    """Prompt the model for a dated study plan over ``[start, end]``."""
    topic_lines = "\n".join(
        f"- id={t.id} | priority={t.priority.value} | {t.title}" for t in topics
    )
    deadline_line = (
        f"- The exam/deadline is on {exam_date.isoformat()} — every topic must be "
        "studied (and exam_critical ones reviewed) before it; leave the final days "
        "for revision.\n"
        if exam_date is not None
        else ""
    )
    return (
        "You are an expert study planner. Build a realistic spaced-repetition "
        f"study plan for the subject \"{subject_name}\".\n\n"
        "Respond with ONLY a JSON object of this exact shape (no prose, no code "
        'fences):\n'
        '{"sessions": [{"topic_id": int, "date": "YYYY-MM-DD", "note": str}]}\n\n'
        "Rules:\n"
        f"- Today is {today.isoformat()}. Schedule every session on a date in the "
        f"inclusive range {start.isoformat()} to {end.isoformat()}.\n"
        f"{deadline_line}"
        "- Use ONLY the topic ids listed below; never invent an id.\n"
        "- Cover every listed topic at least once. Front-load `exam_critical` "
        "topics and give them a second spaced review later if the window allows.\n"
        "- Spread the load evenly across the days; avoid cramming everything onto "
        "one date.\n"
        "- `note` is a short (<= 12 words) reason/focus for that session.\n\n"
        f"# Topics (already-studied topics are omitted)\n{topic_lines}\n"
    )


def parse_plan(text: str) -> list[ParsedSession]:
    """Parse a plan response into sessions. Raises ``PlanParseError`` if unusable.

    Tolerant of malformed individual items (a bad date or non-int id is skipped),
    but requires at least one usable session overall.
    """
    raw = _extract_json_object(text)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise PlanParseError(f"not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
        raise PlanParseError("expected a 'sessions' array")

    sessions: list[ParsedSession] = []
    for item in data["sessions"]:
        if not isinstance(item, dict):
            continue
        topic_id = item.get("topic_id")
        if not isinstance(topic_id, int) or isinstance(topic_id, bool):
            continue
        raw_date = item.get("date")
        if not isinstance(raw_date, str):
            continue
        try:
            on_date = date.fromisoformat(raw_date.strip()[:10])
        except ValueError:
            continue
        note = item.get("note")
        sessions.append(
            ParsedSession(
                topic_id=topic_id,
                on_date=on_date,
                note=note.strip() if isinstance(note, str) else "",
            )
        )
    if not sessions:
        raise PlanParseError("plan contained no usable sessions")
    return sessions


def generate_study_plan(
    session: Session,
    subject_id: int,
    *,
    waterfall: Waterfall | None = None,
    today: date,
    studied_topic_ids: list[int] | None = None,
) -> list[ScheduleEntry]:
    """Generate and persist an AI study plan for a subject. Returns the entries.

    ``studied_topic_ids`` (when given) is the exact set of the subject's topics
    the user has marked already-studied; it is persisted to ``Topic.studied`` and
    those topics are left out of the plan. Raises ``SubjectNotFoundError`` /
    ``NoTopicsToPlanError`` for bad input, ``PlanParseError`` on unusable output;
    provider-exhaustion errors propagate for the router to map to 503.
    ``waterfall`` is injectable for tests.
    """
    subject = session.get(Subject, subject_id)
    if subject is None:
        raise SubjectNotFoundError(subject_id)
    if studied_topic_ids is not None:
        _apply_studied(session, subject_id, set(studied_topic_ids))
    topics = _subject_topics(session, subject_id)
    if not topics:
        raise NoTopicsToPlanError(subject_id)

    if waterfall is None:
        waterfall = build_waterfall_from_settings(get_settings(session))

    start, end = _plan_window(subject, today=today)
    prompt = build_plan_prompt(
        subject.name,
        topics,
        today=today,
        start=start,
        end=end,
        exam_date=subject.exam_date if subject.exam_date and subject.exam_date > today else None,
    )
    result = waterfall.generate(
        prompt, max_tokens=PLAN_MAX_TOKENS, response_schema=PLAN_SCHEMA
    )
    sessions = parse_plan(result.text)

    valid_ids = {t.id for t in topics}
    titles = {t.id: t.title for t in topics}

    # Replace this subject's previous AI plan; keep manual + SM-2 entries.
    topic_ids = list(valid_ids)
    session.execute(
        delete(ScheduleEntry).where(
            ScheduleEntry.topic_id.in_(topic_ids),
            ScheduleEntry.source == ScheduleSource.ai,
        ),
        execution_options={"synchronize_session": "fetch"},
    )

    entries: list[ScheduleEntry] = []
    seen: set[tuple[int, date]] = set()
    for s in sessions:
        if s.topic_id not in valid_ids:
            continue  # model hallucinated an id
        on_date = min(max(s.on_date, start), end)  # clamp into the window
        key = (s.topic_id, on_date)
        if key in seen:
            continue  # dedupe a topic landing twice on one day
        seen.add(key)
        entry = ScheduleEntry(
            topic_id=s.topic_id,
            subject_id=subject_id,
            date=on_date,
            title=titles[s.topic_id],
            description=s.note or None,
            source=ScheduleSource.ai,
        )
        session.add(entry)
        entries.append(entry)

    session.commit()
    for entry in entries:
        session.refresh(entry)
    return entries


def delete_plan(session: Session, subject_id: int) -> int:
    """Delete a subject's AI plan (all ``source=ai`` entries). Returns the count.

    The user's own manual events and the SM-2 calendar are left untouched.
    """
    topic_ids = list(
        session.scalars(
            select(Topic.id)
            .join(Chapter, Topic.chapter_id == Chapter.id)
            .where(Chapter.subject_id == subject_id)
        )
    )
    if not topic_ids:
        return 0
    result = session.execute(
        delete(ScheduleEntry).where(
            ScheduleEntry.topic_id.in_(topic_ids),
            ScheduleEntry.source == ScheduleSource.ai,
        ),
        execution_options={"synchronize_session": "fetch"},
    )
    session.commit()
    return result.rowcount or 0
