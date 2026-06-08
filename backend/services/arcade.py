"""Arcade minigame service — coin economy, runs, upgrades, cooldown, daily quest.

All game-state mutations funnel through here (thin router, logic in the service,
per the project convention). The browser runs the game loop; the server is the
source of truth for currency, records, the anti-binge cooldown, and the daily
quest so none of it can be lost on refresh or trivially fudged.

Tunable knobs live at the top as module constants and are surfaced to the
frontend via ``build_state`` so the shop/HUD render the real numbers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.arcade import (
    SINGLETON_ID,
    ArcadePlaySession,
    ArcadeState,
    ArcadeUpgrade,
)
from backend.models.hierarchy import utcnow

# --- economy tuning ----------------------------------------------------------

COIN_PER_FLASHCARD = 1
COIN_PER_MCQ = 1
DAILY_MCQ_TARGET = 15
DAILY_BONUS_COINS = 1

# Entry costs. Starting fresh from Wave 1 is always the flat base; resuming a
# run pays the base plus the wave you left off at, so deep resumes cost
# progressively more than a fresh start (spec's "base_cost + wave_number").
BASE_COST = 10


def resume_cost(wave: int) -> int:
    return BASE_COST + max(wave, 0)


# Anti-binge cooldown: too many runs *started* within a trailing window locks
# the lever behind a countdown until the oldest runs age out of that window.
COOLDOWN_WINDOW = timedelta(hours=1)
MAX_RUNS_PER_WINDOW = 5


# --- upgrade catalog ---------------------------------------------------------
# Costs are paid from ``score_balance``; ``costs[i]`` buys level i+1. The game
# engine interprets each upgrade's effect; the backend only owns ownership/cost.


@dataclass(frozen=True)
class UpgradeSpec:
    key: str
    name: str
    description: str
    costs: tuple[int, ...]  # one entry per purchasable level

    @property
    def max_level(self) -> int:
        return len(self.costs)


UPGRADE_CATALOG: tuple[UpgradeSpec, ...] = (
    UpgradeSpec(
        "max_health",
        "Reinforced Hull",
        "+1 max health per level — survive more hits.",
        (50, 120, 260, 520),
    ),
    UpgradeSpec(
        "shooting",
        "Sidearm",
        "Unlock the ability to shoot back at enemies.",
        (300,),
    ),
    UpgradeSpec(
        "fire_rate",
        "Rapid Fire",
        "Shoot faster (needs Sidearm).",
        (180, 360, 720),
    ),
    UpgradeSpec(
        "move_speed",
        "Overclock",
        "Dodge projectiles in brief slow-motion.",
        (90, 200, 440),
    ),
    UpgradeSpec(
        "score_multiplier",
        "Combo Chip",
        "+25% score per level.",
        (120, 300, 700),
    ),
)

_CATALOG_BY_KEY = {spec.key: spec for spec in UPGRADE_CATALOG}


# --- errors ------------------------------------------------------------------


class ArcadeError(Exception):
    """Base for arcade rule violations the router maps to HTTP codes."""


class CooldownActiveError(ArcadeError):
    def __init__(self, until: datetime) -> None:
        super().__init__("Arcade cooldown is active")
        self.until = until


class InsufficientCoinsError(ArcadeError):
    pass


class InsufficientScoreError(ArcadeError):
    pass


class NothingToResumeError(ArcadeError):
    pass


class UnknownUpgradeError(ArcadeError):
    pass


class UpgradeMaxedError(ArcadeError):
    pass


class SessionNotFoundError(ArcadeError):
    pass


# --- state plumbing ----------------------------------------------------------


def get_state(session: Session) -> ArcadeState:
    """Return the arcade singleton, creating it on first use (race-safe like
    ``settings.get_settings``), and roll the daily quest if the day changed."""
    state = session.get(ArcadeState, SINGLETON_ID)
    if state is None:
        state = ArcadeState(id=SINGLETON_ID)
        session.add(state)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            state = session.get(ArcadeState, SINGLETON_ID)
        else:
            session.refresh(state)
    if _roll_daily(state, _today()):
        session.commit()
    return state


def _today() -> date:
    return utcnow().date()


def _roll_daily(state: ArcadeState, today: date) -> bool:
    """Reset the daily-quest counters when the stored date isn't today.
    Returns True if anything changed (so the caller can commit)."""
    if state.daily_quest_date == today:
        return False
    state.daily_quest_date = today
    state.daily_mcq_count = 0
    state.daily_bonus_claimed = False
    return True


def _upgrade_levels(session: Session) -> dict[str, int]:
    rows = session.execute(select(ArcadeUpgrade)).scalars().all()
    return {row.key: row.level for row in rows}


def cooldown_until(session: Session, *, now: datetime | None = None) -> datetime | None:
    """When (if ever) the lever returns. ``None`` means playable now.

    Counts runs *started* within the trailing window. With ``T`` allowed and
    ``N >= T`` started, the window drops below ``T`` once ``N - T + 1`` of the
    oldest runs age out — i.e. at ``starts[N - T] + window``.
    """
    now = now or utcnow()
    cutoff = now - COOLDOWN_WINDOW
    starts = (
        session.execute(
            select(ArcadePlaySession.started_at)
            .where(ArcadePlaySession.started_at >= cutoff)
            .order_by(ArcadePlaySession.started_at)
        )
        .scalars()
        .all()
    )
    if len(starts) < MAX_RUNS_PER_WINDOW:
        return None
    until = starts[len(starts) - MAX_RUNS_PER_WINDOW] + COOLDOWN_WINDOW
    return until if until > now else None


# --- operations --------------------------------------------------------------


def earn_coins(session: Session, *, source: str, count: int = 1) -> ArcadeState:
    """Award coins for a study action. ``source`` is 'flashcard' or 'mcq'.

    MCQs advance the daily quest; hitting the target grants the one-per-day
    bonus coin. Validation of ``source``/``count`` is the schema's job.
    """
    state = get_state(session)
    if source == "flashcard":
        state.coins += COIN_PER_FLASHCARD * count
    elif source == "mcq":
        state.coins += COIN_PER_MCQ * count
        state.daily_mcq_count += count
        if (
            state.daily_mcq_count >= DAILY_MCQ_TARGET
            and not state.daily_bonus_claimed
        ):
            state.coins += DAILY_BONUS_COINS
            state.daily_bonus_claimed = True
    else:  # pragma: no cover - schema rejects other sources first
        raise ValueError(f"unknown coin source: {source}")
    session.commit()
    session.refresh(state)
    return state


@dataclass(frozen=True)
class RunStart:
    session_id: int
    start_wave: int
    start_score: int
    cost: int
    coins_after: int


def start_run(session: Session, *, mode: str) -> RunStart:
    """Pay the entry cost and open a play session. ``mode`` is 'fresh'|'resume'.

    Raises ``CooldownActiveError`` while the lever is locked,
    ``NothingToResumeError`` when resuming with no saved run, and
    ``InsufficientCoinsError`` when the balance can't cover the cost.
    """
    state = get_state(session)
    now = utcnow()
    active = cooldown_until(session, now=now)
    if active is not None:
        raise CooldownActiveError(active)

    if mode == "resume":
        if state.resumable_wave <= 0:
            raise NothingToResumeError("no run to resume")
        start_wave = state.resumable_wave
        start_score = state.resumable_score
        cost = resume_cost(start_wave)
    else:  # fresh
        start_wave = 1
        start_score = 0
        cost = BASE_COST

    if state.coins < cost:
        raise InsufficientCoinsError("not enough coins")

    state.coins -= cost
    # Starting consumes the saved run either way: a fresh start abandons it; a
    # resume picks it up (it'll be re-saved on the next death).
    state.resumable_wave = 0
    state.resumable_score = 0

    run = ArcadePlaySession(started_at=now, start_wave=start_wave)
    session.add(run)
    session.commit()
    session.refresh(run)
    session.refresh(state)
    return RunStart(
        session_id=run.id,
        start_wave=start_wave,
        start_score=start_score,
        cost=cost,
        coins_after=state.coins,
    )


def end_run(
    session: Session,
    *,
    session_id: int,
    wave_reached: int,
    score_earned: int,
    died: bool,
) -> ArcadeState:
    """Close a run: bank its score, update records, and (on death) save it as
    the resumable run so the player can pay to continue."""
    run = session.get(ArcadePlaySession, session_id)
    if run is None or run.ended_at is not None:
        raise SessionNotFoundError("no open run with that id")
    state = get_state(session)

    run.ended_at = utcnow()
    run.wave_reached = wave_reached
    run.score_earned = score_earned
    run.died = died

    state.score_balance += score_earned
    state.high_score = max(state.high_score, score_earned)
    state.wave_record = max(state.wave_record, wave_reached)
    if died:
        state.resumable_wave = wave_reached
        state.resumable_score = score_earned

    session.commit()
    session.refresh(state)
    return state


def buy_upgrade(session: Session, *, key: str) -> ArcadeState:
    """Spend ``score_balance`` to buy the next level of an upgrade."""
    spec = _CATALOG_BY_KEY.get(key)
    if spec is None:
        raise UnknownUpgradeError(key)
    state = get_state(session)
    row = session.execute(
        select(ArcadeUpgrade).where(ArcadeUpgrade.key == key)
    ).scalar_one_or_none()
    level = row.level if row is not None else 0
    if level >= spec.max_level:
        raise UpgradeMaxedError(key)
    cost = spec.costs[level]
    if state.score_balance < cost:
        raise InsufficientScoreError("not enough score")
    state.score_balance -= cost
    if row is None:
        row = ArcadeUpgrade(key=key, level=1)
        session.add(row)
    else:
        row.level += 1
    session.commit()
    session.refresh(state)
    return state
