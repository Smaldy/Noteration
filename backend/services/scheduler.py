"""SM-2 spaced-repetition scheduling (Phase 8).

The pure SM-2 core lives here (Phase 8a): it maps the three-button self-grade
(Correct / Incorrect / Skip) to an SM-2 quality score and advances a card's
scheduling state. DB-facing helpers (applying a grade to a ``Flashcard``,
materialising the ``ScheduleEntry`` calendar, deadline mode) build on this core
in later sub-waves of this module.

Per ``docs/ai-pipeline.md`` Stage 4:

  - Correct   → SM-2 success (quality ≥ 3): advance repetitions, grow interval,
                nudge ease up.
  - Incorrect → SM-2 lapse (quality < 3): reset repetitions, interval back to
                1 day, nudge ease down (floored at 1.3).
  - Skip      → no SM-2 change; the card reappears later in the session (triage).

Grade→quality mapping (resolves ``docs/review.md`` "Still open" #3): a 3-button
UI carries no latency signal, so we fix Correct = 5, Incorrect = 2, and treat
Skip as inert (no update at all). The core is pure — no clock, no DB — mirroring
the provider/queue seam; callers inject "today" and own persistence.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

DEFAULT_EASE_FACTOR = 2.5
MIN_EASE_FACTOR = 1.3


class Grade(enum.StrEnum):
    """The three-button self-grade. Transient review input; never persisted."""

    correct = "correct"
    incorrect = "incorrect"
    skip = "skip"


# Self-grade → SM-2 quality (0-5). Skip is intentionally absent: it performs no
# SM-2 update at all (see ``quality_for`` / ``apply_grade``).
_GRADE_QUALITY: dict[Grade, int] = {
    Grade.correct: 5,
    Grade.incorrect: 2,
}


@dataclass(frozen=True)
class CardState:
    """The SM-2 state of a single flashcard (mirrors the ``Flashcard`` fields)."""

    ease_factor: float = DEFAULT_EASE_FACTOR
    interval: int = 0
    repetitions: int = 0


def quality_for(grade: Grade) -> int | None:
    """Return the SM-2 quality (0-5) for a self-grade, or ``None`` for Skip."""
    return _GRADE_QUALITY.get(grade)


def sm2_update(state: CardState, quality: int) -> CardState:
    """Advance ``state`` by one SM-2 review at ``quality`` (0-5).

    ``quality < 3`` is a lapse: repetitions reset to 0 and the interval drops
    back to 1 day. ``quality >= 3`` advances the interval (1 → 6 → round(I·EF)).
    The ease factor is always nudged by the SM-2 response-quality formula and
    floored at ``MIN_EASE_FACTOR``.
    """
    if not 0 <= quality <= 5:
        raise ValueError(f"SM-2 quality must be 0..5, got {quality!r}")

    if quality < 3:
        repetitions = 0
        interval = 1
    elif state.repetitions == 0:
        repetitions, interval = 1, 1
    elif state.repetitions == 1:
        repetitions, interval = 2, 6
    else:
        repetitions = state.repetitions + 1
        # Interval uses the *current* ease factor, before this review's nudge.
        interval = round(state.interval * state.ease_factor)

    delta = 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    ease_factor = max(MIN_EASE_FACTOR, state.ease_factor + delta)
    return CardState(
        ease_factor=ease_factor, interval=interval, repetitions=repetitions
    )


def apply_grade(state: CardState, grade: Grade) -> CardState | None:
    """Advance ``state`` for a self-grade.

    Returns the new state, or ``None`` for Skip (no SM-2 change — the caller
    re-shows the card later in the session without touching scheduling state).
    """
    quality = quality_for(grade)
    if quality is None:
        return None
    return sm2_update(state, quality)
