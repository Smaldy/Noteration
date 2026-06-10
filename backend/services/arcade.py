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

from sqlalchemy import delete, select
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
DAILY_BONUS_COINS = 3

# Entry costs. Starting fresh from Wave 1 is always the flat base; resuming a
# run pays the base plus the wave you left off at, so deep resumes cost
# progressively more than a fresh start (spec's "base_cost + wave_number").
BASE_COST = 3

# A run can be continued (resumed after death) at most this many times; the third
# death ends the lineage and forces a fresh start. A fresh start resets the count.
MAX_CONTINUES = 2


def resume_cost(wave: int) -> int:
    return BASE_COST + max(wave, 0)


def can_resume(state: ArcadeState) -> bool:
    """Whether the saved run may still be continued (one is saved and continues
    aren't exhausted)."""
    return state.resumable_wave > 0 and state.resume_count < MAX_CONTINUES


# Anti-binge cooldown: too many runs *started* within a trailing window locks
# the lever behind a countdown until the oldest runs age out of that window.
COOLDOWN_WINDOW = timedelta(hours=1)
MAX_RUNS_PER_WINDOW = 5


# --- skill catalog -----------------------------------------------------------
# Costs are paid from ``score_balance``; ``cost_at(level)`` buys the next level.
# The game engine interprets each skill's effect; the backend only owns
# ownership, cost, and the tier-unlock gate.
#
# Scalability: a skill is one ``UpgradeSpec`` row — its cost curve is generated
# from ``base_cost``×``growth``^level up to ``max_level`` (no hand-typed tables),
# and ``tier`` groups it under a wave-gated unlock. To add abilities, append a
# row here (and wire its effect in the frontend ``loadoutFrom``); to add a whole
# new tier, append to ``TIER_UNLOCK_WAVE`` and tag skills with that tier.

DEFAULT_MAX_LEVEL = 10
DEFAULT_GROWTH = 1.5  # geometric cost multiplier per owned level

# A tier's skills only become purchasable once the player's best wave
# (``wave_record``) reaches the unlock. Tier 1 is open from the start.
TIER_UNLOCK_WAVE: dict[int, int] = {1: 0, 2: 10, 3: 20}


@dataclass(frozen=True)
class UpgradeSpec:
    key: str
    name: str
    description: str
    tier: int
    base_cost: int  # score cost of the first level
    max_level: int = DEFAULT_MAX_LEVEL
    growth: float = DEFAULT_GROWTH

    def cost_at(self, owned_level: int) -> int:
        """Score cost to buy the ``owned_level+1``-th level (0 = first level)."""
        return round(self.base_cost * (self.growth**owned_level))

    @property
    def costs(self) -> tuple[int, ...]:
        """The full cost curve, one entry per purchasable level."""
        return tuple(self.cost_at(i) for i in range(self.max_level))

    @property
    def unlock_wave(self) -> int:
        return TIER_UNLOCK_WAVE.get(self.tier, 0)


UPGRADE_CATALOG: tuple[UpgradeSpec, ...] = (
    # ── Tier 1 · Core (open from wave 1) ──────────────────────────────────────
    UpgradeSpec(
        "max_health",
        "Reinforced Hull",
        "+1 max health per level — survive more hits.",
        tier=1,
        base_cost=50,
    ),
    UpgradeSpec(
        "zap_damage",
        "Shockwave",
        "+1 click-burst (area) damage per level.",
        tier=1,
        base_cost=60,
    ),
    UpgradeSpec(
        "zap_reach",
        "Resonance Field",
        "+ click-burst radius per level — hit from farther.",
        tier=1,
        base_cost=55,
    ),
    UpgradeSpec(
        "score_multiplier",
        "Combo Chip",
        "+25% score per level.",
        tier=1,
        base_cost=100,
    ),
    # ── Tier 2 · Firepower (unlocks at wave 10) ───────────────────────────────
    UpgradeSpec(
        "shooting",
        "Sidearm",
        "Unlock the click-burst of bullets.",
        tier=2,
        base_cost=300,
        max_level=1,
    ),
    UpgradeSpec(
        "fire_rate",
        "Rapid Fire",
        "+2 bullets per click-burst (needs Sidearm).",
        tier=2,
        base_cost=180,
    ),
    UpgradeSpec(
        "auto_fire",
        "Auto-Turret",
        "Auto-fire at the nearest enemy; faster per level.",
        tier=2,
        base_cost=600,
    ),
    UpgradeSpec(
        "move_speed",
        "Overclock",
        "Dodge projectiles in brief slow-motion.",
        tier=2,
        base_cost=120,
    ),
    # ── Tier 3 · Tactical (unlocks at wave 20) ────────────────────────────────
    UpgradeSpec(
        "defuse_speed",
        "Quick Hands",
        "Defuse bombs faster (shorter hold) per level.",
        tier=3,
        base_cost=140,
    ),
    UpgradeSpec(
        "defuse_window",
        "Long Fuse",
        "+1s on every bomb's fuse per level.",
        tier=3,
        base_cost=130,
    ),
    UpgradeSpec(
        "defuse_freeze",
        "Dampening Field",
        "Slow a bomb's fuse while you defuse it.",
        tier=3,
        base_cost=160,
    ),
    UpgradeSpec(
        "phase_shield",
        "Phase Cloak",
        "Periodic ignore-damage window (30s→20s).",
        tier=3,
        base_cost=220,
    ),
)

_CATALOG_BY_KEY = {spec.key: spec for spec in UPGRADE_CATALOG}

# Highest wave any tier needs — dev tools unlock everything by reaching it.
MAX_TIER_UNLOCK_WAVE = max(TIER_UNLOCK_WAVE.values())


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


class ContinueLimitError(ArcadeError):
    """The run lineage has used up its allotted continues — start fresh."""


class UnknownUpgradeError(ArcadeError):
    pass


class UpgradeMaxedError(ArcadeError):
    pass


class TierLockedError(ArcadeError):
    """The skill's tier hasn't been unlocked yet (wave_record too low)."""

    def __init__(self, unlock_wave: int) -> None:
        super().__init__(f"reach wave {unlock_wave} to unlock this tier")
        self.unlock_wave = unlock_wave


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


def start_run(session: Session, *, mode: str, dev: bool = False) -> RunStart:
    """Pay the entry cost and open a play session. ``mode`` is 'fresh'|'resume'.

    Raises ``CooldownActiveError`` while the lever is locked,
    ``NothingToResumeError`` when resuming with no saved run, and
    ``InsufficientCoinsError`` when the balance can't cover the cost.

    ``dev`` (local developer mode) skips the anti-binge cooldown so runs can be
    started back-to-back while testing.
    """
    state = get_state(session)
    now = utcnow()
    if not dev:
        active = cooldown_until(session, now=now)
        if active is not None:
            raise CooldownActiveError(active)

    if mode == "resume":
        if state.resumable_wave <= 0:
            raise NothingToResumeError("no run to resume")
        if state.resume_count >= MAX_CONTINUES:
            raise ContinueLimitError("continue limit reached — start fresh")
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
    # Starting consumes the saved run either way: a fresh start abandons it and
    # begins a new lineage (continues reset); a resume picks it up and spends one
    # continue (it'll be re-saved on the next death).
    state.resumable_wave = 0
    state.resumable_score = 0
    if mode == "resume":
        state.resume_count += 1
    else:
        state.resume_count = 0

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
    if state.wave_record < spec.unlock_wave:
        raise TierLockedError(spec.unlock_wave)
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


# --- developer tools ---------------------------------------------------------
# Local-only helpers surfaced behind a frontend ``DEV_MODE`` flag, so the user
# can exercise the shop without grinding. Not wired into any normal game flow.

DEV_GRANT_AMOUNT = 1_000_000


def dev_grant(session: Session) -> ArcadeState:
    """Top coins + score up to a huge balance for testing (effectively infinite),
    and unlock every skill tier so the whole shop is exercisable locally."""
    state = get_state(session)
    state.coins = DEV_GRANT_AMOUNT
    state.score_balance = DEV_GRANT_AMOUNT
    state.wave_record = max(state.wave_record, MAX_TIER_UNLOCK_WAVE)
    session.commit()
    session.refresh(state)
    return state


def dev_reset_upgrades(session: Session) -> ArcadeState:
    """Clear every owned upgrade back to level 0 so purchases can be re-tested."""
    session.execute(delete(ArcadeUpgrade))
    session.commit()
    return get_state(session)
