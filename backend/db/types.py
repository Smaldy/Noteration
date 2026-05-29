"""Custom column types.

``UTCDateTime`` keeps every stored datetime timezone-aware UTC. SQLite has no
native timezone, so a plain ``DateTime`` round-trips aware values as *naive* —
which then can't be compared to ``datetime.now(timezone.utc)`` (e.g. the queue
comparing ``resume_after`` to now for wake-up scheduling). This decorator
normalizes on the way in and re-attaches UTC on the way out.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
