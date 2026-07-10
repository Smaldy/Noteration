"""TodoItem — a topic pinned to the floating to-do list.

The list is just an ordered set of topic references: an item's "checked" state
is not stored here but derived from ``Topic.studied``, so the Notes-tab
checkmark, the calendar, and the to-do list can never disagree. One row per
topic (unique), cascade-deleted with it.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base
from backend.db.types import UTCDateTime
from backend.models.hierarchy import utcnow

if TYPE_CHECKING:
    from backend.models.hierarchy import Topic


class TodoItem(Base):
    __tablename__ = "todo_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), unique=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    topic: Mapped[Topic] = relationship()
