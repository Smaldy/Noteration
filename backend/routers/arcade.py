"""/arcade — the study-gated minigame's economy + run/upgrade state.

Fully additive: these endpoints back a non-destructive overlay in the frontend.
Thin router; all rules live in ``services.arcade``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.schemas.arcade import (
    ArcadeStateOut,
    DailyQuestOut,
    EarnRequest,
    EconomyOut,
    EndRunRequest,
    RunStartOut,
    StartRunRequest,
    UpgradeOut,
)
from backend.services import arcade as arcade_service

router = APIRouter(prefix="/arcade", tags=["arcade"])


def build_state_out(session: Session) -> ArcadeStateOut:
    """Assemble the full client-facing state from service primitives."""
    state = arcade_service.get_state(session)
    levels = arcade_service._upgrade_levels(session)
    upgrades = [
        UpgradeOut(
            key=spec.key,
            name=spec.name,
            description=spec.description,
            level=levels.get(spec.key, 0),
            max_level=spec.max_level,
            next_cost=(
                spec.cost_at(levels.get(spec.key, 0))
                if levels.get(spec.key, 0) < spec.max_level
                else None
            ),
            tier=spec.tier,
            unlock_wave=spec.unlock_wave,
            locked=state.wave_record < spec.unlock_wave,
        )
        for spec in arcade_service.UPGRADE_CATALOG
    ]
    return ArcadeStateOut(
        coins=state.coins,
        score_balance=state.score_balance,
        high_score=state.high_score,
        wave_record=state.wave_record,
        resumable_wave=state.resumable_wave,
        resumable_score=state.resumable_score,
        resume_cost=(
            arcade_service.resume_cost(state.resumable_wave)
            if arcade_service.can_resume(state)
            else None
        ),
        resume_count=state.resume_count,
        max_continues=arcade_service.MAX_CONTINUES,
        cooldown_until=arcade_service.cooldown_until(session),
        daily_quest=DailyQuestOut(
            mcq_count=state.daily_mcq_count,
            target=arcade_service.DAILY_MCQ_TARGET,
            bonus_claimed=state.daily_bonus_claimed,
            completed=state.daily_mcq_count >= arcade_service.DAILY_MCQ_TARGET,
        ),
        upgrades=upgrades,
        economy=EconomyOut(
            coin_per_flashcard=arcade_service.COIN_PER_FLASHCARD,
            coin_per_mcq=arcade_service.COIN_PER_MCQ,
            base_cost=arcade_service.BASE_COST,
        ),
        prestige_count=state.prestige_count,
        can_prestige=arcade_service.can_prestige(state),
        prestige_unlock_wave=arcade_service.PRESTIGE_UNLOCK_WAVE,
        active_special=state.active_special,
        specials=list(arcade_service.SPECIALS),
    )


@router.get("/state", response_model=ArcadeStateOut)
def get_state(db: Session = Depends(get_session)) -> ArcadeStateOut:
    return build_state_out(db)


@router.post("/coins/earn", response_model=ArcadeStateOut)
def earn_coins(
    payload: EarnRequest, db: Session = Depends(get_session)
) -> ArcadeStateOut:
    arcade_service.earn_coins(db, source=payload.source, count=payload.count)
    return build_state_out(db)


@router.post("/run/start", response_model=RunStartOut)
def start_run(
    payload: StartRunRequest, db: Session = Depends(get_session)
) -> RunStartOut:
    try:
        run = arcade_service.start_run(db, mode=payload.mode, dev=payload.dev)
    except arcade_service.CooldownActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"reason": "cooldown", "cooldown_until": exc.until.isoformat()},
        )
    except arcade_service.NothingToResumeError:
        raise HTTPException(status_code=409, detail="No run to resume")
    except arcade_service.ContinueLimitError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Continue limit reached — start a new game",
        )
    except arcade_service.InsufficientCoinsError:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Not enough coins",
        )
    return RunStartOut(
        session_id=run.session_id,
        start_wave=run.start_wave,
        start_score=run.start_score,
        cost=run.cost,
        coins_after=run.coins_after,
    )


@router.post("/run/end", response_model=ArcadeStateOut)
def end_run(
    payload: EndRunRequest, db: Session = Depends(get_session)
) -> ArcadeStateOut:
    try:
        arcade_service.end_run(
            db,
            session_id=payload.session_id,
            wave_reached=payload.wave_reached,
            score_earned=payload.score_earned,
            died=payload.died,
        )
    except arcade_service.SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found or already ended")
    return build_state_out(db)


@router.post("/prestige", response_model=ArcadeStateOut)
def prestige(db: Session = Depends(get_session)) -> ArcadeStateOut:
    try:
        arcade_service.prestige(db)
    except arcade_service.PrestigeLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reach wave {exc.unlock_wave} to prestige",
        )
    return build_state_out(db)


@router.post("/special/{special}", response_model=ArcadeStateOut)
def set_special(special: str, db: Session = Depends(get_session)) -> ArcadeStateOut:
    try:
        arcade_service.set_special(db, special=special)
    except arcade_service.UnknownSpecialError:
        raise HTTPException(status_code=404, detail="Unknown special bullet")
    except arcade_service.SpecialLockedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Prestige to unlock special bullets",
        )
    return build_state_out(db)


@router.post("/dev/grant", response_model=ArcadeStateOut)
def dev_grant(db: Session = Depends(get_session)) -> ArcadeStateOut:
    """Developer tool: top up coins + score (local testing only)."""
    arcade_service.dev_grant(db)
    return build_state_out(db)


@router.post("/dev/reset-upgrades", response_model=ArcadeStateOut)
def dev_reset_upgrades(db: Session = Depends(get_session)) -> ArcadeStateOut:
    """Developer tool: reset all owned upgrades to level 0 (local testing only)."""
    arcade_service.dev_reset_upgrades(db)
    return build_state_out(db)


@router.post("/dev/reset-prestige", response_model=ArcadeStateOut)
def dev_reset_prestige(db: Session = Depends(get_session)) -> ArcadeStateOut:
    """Developer tool: wipe prestige progress (local testing only)."""
    arcade_service.dev_reset_prestige(db)
    return build_state_out(db)


@router.post("/dev/reset-score", response_model=ArcadeStateOut)
def dev_reset_score(db: Session = Depends(get_session)) -> ArcadeStateOut:
    """Developer tool: zero the score balance (local testing only)."""
    arcade_service.dev_reset_score(db)
    return build_state_out(db)


@router.post("/dev/reset-coins", response_model=ArcadeStateOut)
def dev_reset_coins(db: Session = Depends(get_session)) -> ArcadeStateOut:
    """Developer tool: zero the coin balance (local testing only)."""
    arcade_service.dev_reset_coins(db)
    return build_state_out(db)


@router.post("/dev/max-upgrades", response_model=ArcadeStateOut)
def dev_max_upgrades(db: Session = Depends(get_session)) -> ArcadeStateOut:
    """Developer tool: own every upgrade at max level (local testing only)."""
    arcade_service.dev_max_upgrades(db)
    return build_state_out(db)


@router.post("/dev/unlock-tiers", response_model=ArcadeStateOut)
def dev_unlock_tiers(db: Session = Depends(get_session)) -> ArcadeStateOut:
    """Developer tool: ignore the per-tier wave restriction (local testing only)."""
    arcade_service.dev_unlock_tiers(db)
    return build_state_out(db)


@router.post("/upgrades/{key}/buy", response_model=ArcadeStateOut)
def buy_upgrade(key: str, db: Session = Depends(get_session)) -> ArcadeStateOut:
    try:
        arcade_service.buy_upgrade(db, key=key)
    except arcade_service.UnknownUpgradeError:
        raise HTTPException(status_code=404, detail="Unknown upgrade")
    except arcade_service.UpgradeMaxedError:
        raise HTTPException(status_code=409, detail="Upgrade already maxed")
    except arcade_service.TierLockedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Reach wave {exc.unlock_wave} to unlock this tier",
        )
    except arcade_service.InsufficientScoreError:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Not enough score points",
        )
    return build_state_out(db)
