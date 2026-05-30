"""Phase 8a — pure SM-2 core tests (no DB, no clock)."""

from __future__ import annotations

import pytest

from backend.services.scheduler import (
    DEFAULT_EASE_FACTOR,
    MIN_EASE_FACTOR,
    CardState,
    Grade,
    apply_grade,
    quality_for,
    sm2_update,
)


def test_grade_to_quality_mapping():
    assert quality_for(Grade.correct) == 5
    assert quality_for(Grade.incorrect) == 2
    assert quality_for(Grade.skip) is None


def test_first_correct_review_schedules_one_day():
    state = sm2_update(CardState(), 5)  # fresh card, perfect recall
    assert state.repetitions == 1
    assert state.interval == 1
    assert state.ease_factor == pytest.approx(2.6)


def test_second_correct_review_schedules_six_days():
    state = sm2_update(CardState(ease_factor=2.6, interval=1, repetitions=1), 5)
    assert state.repetitions == 2
    assert state.interval == 6
    assert state.ease_factor == pytest.approx(2.7)


def test_third_correct_review_uses_ease_factor():
    # round(6 * 2.7) == 16
    state = sm2_update(CardState(ease_factor=2.7, interval=6, repetitions=2), 5)
    assert state.repetitions == 3
    assert state.interval == 16
    assert state.ease_factor == pytest.approx(2.8)


def test_incorrect_resets_repetitions_and_interval():
    # A mature card lapses: q=2 (< 3) → relearn from 1 day, repetitions reset.
    state = sm2_update(CardState(ease_factor=2.5, interval=16, repetitions=5), 2)
    assert state.repetitions == 0
    assert state.interval == 1
    # delta(q=2) = 0.1 - 3*(0.08 + 3*0.02) = -0.32
    assert state.ease_factor == pytest.approx(2.18)


def test_ease_factor_floored():
    # Already near the floor; a lapse must not push EF below MIN_EASE_FACTOR.
    state = sm2_update(CardState(ease_factor=1.4, interval=10, repetitions=4), 2)
    assert state.ease_factor == MIN_EASE_FACTOR


def test_quality_out_of_range_raises():
    with pytest.raises(ValueError):
        sm2_update(CardState(), 6)
    with pytest.raises(ValueError):
        sm2_update(CardState(), -1)


def test_card_state_defaults_match_flashcard_columns():
    s = CardState()
    assert s.ease_factor == DEFAULT_EASE_FACTOR == 2.5
    assert s.interval == 0
    assert s.repetitions == 0


def test_apply_grade_skip_is_inert():
    state = CardState(ease_factor=2.5, interval=6, repetitions=2)
    assert apply_grade(state, Grade.skip) is None


def test_apply_grade_matches_sm2_update():
    base = CardState(ease_factor=2.5, interval=6, repetitions=2)
    assert apply_grade(base, Grade.correct) == sm2_update(base, 5)
    assert apply_grade(base, Grade.incorrect) == sm2_update(base, 2)
