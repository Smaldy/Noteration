"""Local budget trackers for the provider budget probes.

We can't query a provider's server-side remaining quota, so we model it locally
from our own call history: free tiers by requests/min + requests/day (the binding
axis wins). Time is injected so the trackers are deterministic and testable. See
docs/architecture.md "Budget-aware dispatch".
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

_MINUTE = timedelta(minutes=1)
_DAY = timedelta(days=1)


@dataclass
class FreeTierSnapshot:
    available: bool
    headroom: int  # requests that still fit on the binding axis
    binding_axis: str  # 'rpm' | 'rpd'
    reset_at: datetime | None


@dataclass
class FreeTierLimiter:
    """Tracks requests-per-minute and requests-per-day; reports the binding axis."""

    rpm: int
    rpd: int
    _minute: deque[datetime] = field(default_factory=deque)
    _day: deque[datetime] = field(default_factory=deque)

    def record(self, now: datetime) -> None:
        self._minute.append(now)
        self._day.append(now)

    def snapshot(self, now: datetime) -> FreeTierSnapshot:
        self._prune(now)
        rpm_left = max(0, self.rpm - len(self._minute))
        rpd_left = max(0, self.rpd - len(self._day))
        # The axis with less headroom binds; ties go to the minute window (it
        # reopens soonest, so it's the more useful reset to report).
        if rpm_left <= rpd_left:
            axis, left, bucket, window = "rpm", rpm_left, self._minute, _MINUTE
        else:
            axis, left, bucket, window = "rpd", rpd_left, self._day, _DAY
        if left > 0:
            return FreeTierSnapshot(True, left, axis, None)
        reset_at = bucket[0] + window if bucket else None
        return FreeTierSnapshot(False, 0, axis, reset_at)

    def _prune(self, now: datetime) -> None:
        while self._minute and now - self._minute[0] >= _MINUTE:
            self._minute.popleft()
        while self._day and now - self._day[0] >= _DAY:
            self._day.popleft()
