"""Arcade minigame request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --- requests ----------------------------------------------------------------


class EarnRequest(BaseModel):
    source: Literal["flashcard", "mcq"]
    count: int = Field(default=1, ge=1, le=1000)


class StartRunRequest(BaseModel):
    mode: Literal["fresh", "resume"] = "fresh"
    # Local developer mode: skip the anti-binge cooldown. Set only by the
    # frontend DEV_MODE panel (single-user local app; never shipped enabled).
    dev: bool = False


class EndRunRequest(BaseModel):
    session_id: int
    wave_reached: int = Field(ge=0)
    score_earned: int = Field(ge=0)
    died: bool = True


# --- responses ---------------------------------------------------------------


class UpgradeOut(BaseModel):
    key: str
    name: str
    description: str
    level: int
    max_level: int
    next_cost: int | None  # None when fully upgraded
    tier: int  # 1..5 — skills are grouped and gated by tier
    unlock_wave: int  # wave_record needed to buy this tier (0 = always open)
    locked: bool  # True while wave_record < unlock_wave


class DailyQuestOut(BaseModel):
    mcq_count: int
    target: int
    bonus_claimed: bool
    completed: bool


class EconomyOut(BaseModel):
    coin_per_flashcard: int
    coin_per_mcq: int
    base_cost: int


class ArcadeStateOut(BaseModel):
    coins: int
    score_balance: int
    high_score: int
    wave_record: int
    resumable_wave: int
    resumable_score: int
    resume_cost: int | None  # cost to resume the saved run, None if none/exhausted
    resume_count: int  # continues used on the current run lineage
    max_continues: int  # how many continues a lineage allows before a forced fresh
    cooldown_until: datetime | None
    daily_quest: DailyQuestOut
    upgrades: list[UpgradeOut]
    economy: EconomyOut
    # Prestige / special bullets (tier 6).
    prestige_count: int
    can_prestige: bool  # final tier reached → a prestige is allowed
    prestige_unlock_wave: int  # wave_record needed to prestige
    active_special: str  # "none" | "electric" | "love"
    specials: list[str]  # the selectable special-bullet ids


class RunStartOut(BaseModel):
    session_id: int
    start_wave: int
    start_score: int
    cost: int
    coins_after: int
