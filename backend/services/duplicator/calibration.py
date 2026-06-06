"""Calibration samples — topic+year examples that ground the variant search.

``recent_samples`` (read) feeds the search prompt; ``add_sample`` records an
exercise as an example; ``export_calibration`` / ``import_calibration`` move the
corpus between installs so a cold start can be seeded.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.duplicator import CalibrationSample
from backend.models.enums import CalibrationSource

# How many examples to feed the search prompt for a topic+year.
MAX_PROMPT_SAMPLES = 5
# Version stamp on exported corpora, so a future format change can be detected.
SCHEMA_VERSION = 1


def recent_samples(
    session: Session, topic: str, year_level: int, *, limit: int = MAX_PROMPT_SAMPLES
) -> list[CalibrationSample]:
    """Newest-first calibration samples matching ``topic`` and ``year_level``.

    Empty on cold start (no samples yet) — the search prompt then omits the
    examples section entirely rather than fabricating any.
    """
    return list(
        session.scalars(
            select(CalibrationSample)
            .where(
                CalibrationSample.topic == topic,
                CalibrationSample.year_level == year_level,
            )
            .order_by(CalibrationSample.created_at.desc(), CalibrationSample.id.desc())
            .limit(limit)
        )
    )


def add_sample(
    session: Session,
    *,
    topic: str,
    subtopic: str | None,
    year_level: int,
    source_text: str,
    source: CalibrationSource = CalibrationSource.own,
    commit: bool = True,
) -> CalibrationSample:
    """Record one calibration sample. ``commit=False`` to batch into a caller txn.

    Called per exercise from ``create_session`` (``own``) and by the "Save to
    calibration" button (also ``own``); import uses ``source=imported``.
    """
    sample = CalibrationSample(
        topic=topic,
        subtopic=subtopic or None,
        year_level=year_level,
        source_text=source_text,
        source=source,
    )
    session.add(sample)
    if commit:
        session.commit()
        session.refresh(sample)
    return sample


def export_calibration(session: Session) -> dict[str, Any]:
    """All calibration samples as a JSON-serialisable dict (with a schema stamp)."""
    samples = session.scalars(
        select(CalibrationSample).order_by(CalibrationSample.id)
    ).all()
    return {
        "schema_version": SCHEMA_VERSION,
        "samples": [
            {
                "topic": s.topic,
                "subtopic": s.subtopic,
                "year_level": s.year_level,
                "source_text": s.source_text,
                "source": s.source.value,
            }
            for s in samples
        ],
    }


def _is_duplicate_sample(
    session: Session,
    *,
    topic: str,
    subtopic: str | None,
    year_level: int,
    source_text: str,
) -> bool:
    """True when an identical sample (topic+subtopic+year+text) already exists."""
    return (
        session.scalar(
            select(CalibrationSample.id).where(
                CalibrationSample.topic == topic,
                CalibrationSample.subtopic == subtopic,
                CalibrationSample.year_level == year_level,
                CalibrationSample.source_text == source_text,
            )
        )
        is not None
    )


def import_calibration(session: Session, data: dict[str, Any]) -> tuple[int, int]:
    """Import samples from an exported dict. Returns ``(imported, skipped)``.

    Exact duplicates (same topic+subtopic+year_level+source_text) are skipped;
    malformed rows are skipped; imported rows are tagged ``source=imported``.
    """
    rows = data.get("samples") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return 0, 0

    imported = 0
    skipped = 0
    for row in rows:
        if not isinstance(row, dict):
            skipped += 1
            continue
        topic = row.get("topic")
        source_text = row.get("source_text")
        year_level = row.get("year_level")
        if not (
            isinstance(topic, str)
            and topic.strip()
            and isinstance(source_text, str)
            and source_text.strip()
            and isinstance(year_level, int)
            and not isinstance(year_level, bool)
        ):
            skipped += 1
            continue
        raw_sub = row.get("subtopic")
        subtopic = raw_sub.strip() if isinstance(raw_sub, str) and raw_sub.strip() else None
        if _is_duplicate_sample(
            session,
            topic=topic,
            subtopic=subtopic,
            year_level=year_level,
            source_text=source_text,
        ):
            skipped += 1
            continue
        session.add(
            CalibrationSample(
                topic=topic,
                subtopic=subtopic,
                year_level=year_level,
                source_text=source_text,
                source=CalibrationSource.imported,
            )
        )
        imported += 1
    session.commit()
    return imported, skipped
