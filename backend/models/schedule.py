"""ScheduleEntry — a topic's place on the SM-2 / deadline study calendar."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base
from backend.models.enums import ScheduleSource

if TYPE_CHECKING:
    from backend.models.hierarchy import Topic


class ScheduleEntry(Base):
    __tablename__ = "schedule_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    date: Mapped[date]
    is_revision_buffer: Mapped[bool] = mapped_column(default=False)
    source: Mapped[ScheduleSource] = mapped_column(
        SAEnum(ScheduleSource, native_enum=False), default=ScheduleSource.sm2
    )

    topic: Mapped[Topic] = relationship(back_populates="schedule_entries")
