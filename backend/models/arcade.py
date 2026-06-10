"""Arcade minigame state — a fully additive feature layer.

Single-user local app, so the player's economy lives in one singleton row
(``ArcadeState``, id is always 1), mirroring the ``Settings`` pattern. Owned
upgrades are rows keyed by upgrade ``key``; each run is logged as an
``ArcadePlaySession`` (used both for run history and the rolling-window cooldown
that discourages binge play). Nothing here touches the study models.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base
from backend.db.types import UTCDateTime
from backend.models.hierarchy import utcnow

SINGLETON_ID = 1


class ArcadeState(Base):
    """The single player's persistent arcade economy + records (id == 1)."""

    __tablename__ = "arcade_state"

    id: Mapped[int] = mapped_column(primary_key=True, default=SINGLETON_ID)
    # Entry currency, earned only by studying (flashcards / MCQs).
    coins: Mapped[int] = mapped_column(default=0)
    # Spendable upgrade currency, banked from run scores.
    score_balance: Mapped[int] = mapped_column(default=0)
    # Records.
    high_score: Mapped[int] = mapped_column(default=0)
    wave_record: Mapped[int] = mapped_column(default=0)
    # Resumable run left behind on death (0 = no run to resume).
    resumable_wave: Mapped[int] = mapped_column(default=0)
    resumable_score: Mapped[int] = mapped_column(default=0)
    # How many times the current run lineage has been continued. A fresh start
    # resets it; once it hits MAX_CONTINUES the run can no longer be resumed.
    resume_count: Mapped[int] = mapped_column(default=0)
    # Daily quest (complete N MCQs in a day → bonus coin). Counter resets when
    # ``daily_quest_date`` no longer matches the server's UTC "today".
    daily_mcq_count: Mapped[int] = mapped_column(default=0)
    daily_quest_date: Mapped[date | None] = mapped_column(default=None)
    daily_bonus_claimed: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow
    )


class ArcadeUpgrade(Base):
    """One row per purchased upgrade; ``level`` is how many tiers are owned."""

    __tablename__ = "arcade_upgrades"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(unique=True)
    level: Mapped[int] = mapped_column(default=0)


class ArcadePlaySession(Base):
    """A single run: opened on start, closed on end. Also the cooldown ledger
    (runs started within the trailing hour gate further play)."""

    __tablename__ = "arcade_play_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(UTCDateTime, default=None)
    start_wave: Mapped[int] = mapped_column(default=1)
    wave_reached: Mapped[int] = mapped_column(default=0)
    score_earned: Mapped[int] = mapped_column(default=0)
    died: Mapped[bool] = mapped_column(default=False)
