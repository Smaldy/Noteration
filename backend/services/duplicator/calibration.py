"""Calibration samples — topic+year examples that ground the variant search.

ED-3 only needs the read side (``recent_samples``) to feed the search prompt; the
write side (``add_sample``) and export/import land in ED-4.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.duplicator import CalibrationSample

# How many examples to feed the search prompt for a topic+year.
MAX_PROMPT_SAMPLES = 5


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
