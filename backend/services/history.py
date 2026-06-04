"""Generation-history log (Wave C).

The cost-visibility/transparency surface that replaces the previously-planned
overnight notification: an append-only log of *which provider generated what, how
long it took*, and *when the active provider switched* (e.g. Ollama→Gemini at a
reset window). The switch is derived from the log itself — the last recorded
generation provider — so there's no extra worker state to keep in sync and
"switched from X to Y" is always reconstructable from the rows.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from backend.models.enums import HistoryEventType
from backend.models.hierarchy import Subject, Topic, utcnow
from backend.models.processing import HistoryEvent

logger = logging.getLogger("backend.history")

HistoryClearScope = Literal["hour", "day", "all"]

# How far back each scope reaches; "all" clears everything (no cutoff).
_CLEAR_WINDOWS: dict[str, timedelta] = {
    "hour": timedelta(hours=1),
    "day": timedelta(days=1),
}


@dataclass
class HistoryEventView:
    """A history row enriched with subject/topic names for display."""

    id: int
    event_type: str
    subject_id: int | None
    subject_name: str | None
    topic_id: int | None
    topic_title: str | None
    provider_from: str | None
    provider_to: str | None
    detail: str | None
    created_at: datetime


def last_generation_provider(session: Session) -> str | None:
    """Provider of the most recent ``topic_generated`` event (for switch detection)."""
    return session.scalars(
        select(HistoryEvent.provider_to)
        .where(HistoryEvent.event_type == HistoryEventType.topic_generated)
        .order_by(HistoryEvent.id.desc())
    ).first()


def record_generation(
    session: Session,
    *,
    topic_id: int,
    subject_id: int | None,
    provider: str,
    seconds: float | None,
    commit: bool = True,
) -> list[HistoryEvent]:
    """Log a topic generation; if the provider changed, log a switch first.

    Append-only. Returns the events created (a ``provider_switch`` then a
    ``topic_generated``, or just the latter when the provider is unchanged).
    """
    events: list[HistoryEvent] = []
    previous = last_generation_provider(session)
    if previous is not None and previous != provider:
        switch = HistoryEvent(
            event_type=HistoryEventType.provider_switch,
            subject_id=subject_id,
            provider_from=previous,
            provider_to=provider,
            detail=f"switched from {previous} to {provider}",
        )
        session.add(switch)
        events.append(switch)
    generated = HistoryEvent(
        event_type=HistoryEventType.topic_generated,
        subject_id=subject_id,
        topic_id=topic_id,
        provider_to=provider,
        detail=None if seconds is None else f"{seconds:.1f}s",
    )
    session.add(generated)
    events.append(generated)
    if commit:
        session.commit()
    return events


def record_generation_safe(
    session: Session,
    *,
    topic_id: int,
    subject_id: int | None,
    provider: str,
    seconds: float | None,
) -> None:
    """Best-effort ``record_generation`` — history must never break a drain."""
    try:
        record_generation(
            session,
            topic_id=topic_id,
            subject_id=subject_id,
            provider=provider,
            seconds=seconds,
        )
    except Exception:  # noqa: BLE001 - the audit log is non-critical
        logger.exception("Failed to record generation history event")
        session.rollback()


def clear_history(
    session: Session,
    *,
    scope: HistoryClearScope = "all",
    now: datetime | None = None,
    commit: bool = True,
) -> int:
    """Delete history rows for the given scope; returns how many were removed.

    ``hour``/``day`` keep older events and only drop the recent window (cutoff is
    ``now - window``, ``now`` injectable for testing); ``all`` wipes the whole log.
    Idempotent — clearing an already-empty window deletes nothing.
    """
    stmt = delete(HistoryEvent)
    window = _CLEAR_WINDOWS.get(scope)
    if window is not None:
        cutoff = (now or utcnow()) - window
        stmt = stmt.where(HistoryEvent.created_at >= cutoff)
    result = session.execute(stmt)
    if commit:
        session.commit()
    return result.rowcount or 0


def recent_events(
    session: Session, *, subject_id: int | None = None, limit: int = 100
) -> list[HistoryEvent]:
    """Most-recent-first history. A ``subject_id`` narrows to that subject's events
    plus global (subject-less) events like provider switches.
    """
    query = select(HistoryEvent).order_by(
        HistoryEvent.created_at.desc(), HistoryEvent.id.desc()
    )
    if subject_id is not None:
        query = query.where(
            or_(
                HistoryEvent.subject_id == subject_id,
                HistoryEvent.subject_id.is_(None),
            )
        )
    return list(session.scalars(query.limit(limit)).all())


def recent_events_view(
    session: Session, *, subject_id: int | None = None, limit: int = 100
) -> list[HistoryEventView]:
    """Most-recent-first history enriched with subject/topic names (one query,
    no N+1). A ``subject_id`` narrows to that subject's events plus global ones.
    """
    query = (
        select(HistoryEvent, Subject.name, Topic.title)
        .outerjoin(Subject, HistoryEvent.subject_id == Subject.id)
        .outerjoin(Topic, HistoryEvent.topic_id == Topic.id)
        .order_by(HistoryEvent.created_at.desc(), HistoryEvent.id.desc())
    )
    if subject_id is not None:
        query = query.where(
            or_(
                HistoryEvent.subject_id == subject_id,
                HistoryEvent.subject_id.is_(None),
            )
        )
    return [
        HistoryEventView(
            id=event.id,
            event_type=str(event.event_type),
            subject_id=event.subject_id,
            subject_name=subject_name,
            topic_id=event.topic_id,
            topic_title=topic_title,
            provider_from=event.provider_from,
            provider_to=event.provider_to,
            detail=event.detail,
            created_at=event.created_at,
        )
        for event, subject_name, topic_title in session.execute(query.limit(limit)).all()
    ]
