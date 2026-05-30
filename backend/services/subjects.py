"""Subject service — list + create.

Thin by design: a subject is just a name (+ optional accent color and exam
date) at the top of the hierarchy. The upload UI lists subjects to pick from
and creates one inline when needed. The service owns its transaction.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Subject


def list_subjects(session: Session) -> list[Subject]:
    """All subjects, name-sorted (case-insensitive) for the picker."""
    return list(
        session.execute(
            select(Subject).order_by(func.lower(Subject.name), Subject.id)
        ).scalars()
    )


def create_subject(
    session: Session,
    *,
    name: str,
    accent_color: str | None = None,
    exam_date: date | None = None,
) -> Subject:
    """Create and persist a subject. Name is trimmed; no uniqueness enforced."""
    subject = Subject(
        name=name.strip(),
        accent_color=accent_color,
        exam_date=exam_date,
    )
    session.add(subject)
    session.commit()
    session.refresh(subject)
    return subject
