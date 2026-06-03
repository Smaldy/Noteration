"""ScheduleEntry — a topic's place on the SM-2 / deadline study calendar.

Originally a pure projection of flashcard due dates (one row per topic+date). It
now also backs **user-authored** calendar items: a custom free-text event (no
topic), a "study this topic" session, or a "study this subject" session — plus a
``completed``/``completed_at`` pair so a session can be checked off (and judged
on-time vs late against its scheduled ``date``). ``topic_id`` is therefore
nullable; ``subject_id`` links whole-subject and AI-plan entries so they cascade
away with the subject. See docs/build-log.md (calendar manual-events fix).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base
from backend.models.enums import ScheduleSource

if TYPE_CHECKING:
    from backend.models.hierarchy import Subject, Topic


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable: a custom event has no topic; a whole-subject session links a
    # subject instead. SM-2/topic sessions still set topic_id.
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), nullable=True
    )
    subject_id: Mapped[int | None] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), nullable=True
    )
    date: Mapped[date]
    # User-supplied event name; for topic/subject sessions this falls back to the
    # topic/subject name at read time when left blank.
    title: Mapped[str | None] = mapped_column(default=None)
    description: Mapped[str | None] = mapped_column(default=None)
    completed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[date | None] = mapped_column(default=None)
    # A deadline/exam marker (rendered bloody red). Tied to a subject; creating /
    # moving / deleting one keeps ``Subject.exam_date`` in sync so the AI planner
    # and SM-2 deadline mode optimise toward it.
    is_deadline: Mapped[bool] = mapped_column(default=False)
    is_revision_buffer: Mapped[bool] = mapped_column(default=False)
    source: Mapped[ScheduleSource] = mapped_column(
        SAEnum(ScheduleSource, native_enum=False), default=ScheduleSource.sm2
    )

    topic: Mapped[Topic | None] = relationship(back_populates="schedule_entries")
    subject: Mapped[Subject | None] = relationship()
