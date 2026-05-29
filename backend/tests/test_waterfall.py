"""Waterfall tests: cheapest-first, failover, single-wake-up backoff, vision.

These cover the reliability rules from cost-strategy.md: try cheapest first,
fail over on limit/hard error, cool a limited provider until its reset, apply
exponential backoff to a flaky one, and when all are exhausted surface the
earliest reset time (never spin).
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.services.providers import (
    AllProvidersExhausted,
    MockProvider,
    ProviderLimitError,
    ProviderUnavailableError,
    Waterfall,
)

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


class Clock:
    """Controllable clock for deterministic cooldown/backoff tests."""

    def __init__(self, now: datetime = BASE) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def test_picks_cheapest_first_and_stamps_provider() -> None:
    first = MockProvider("a", text="from-a")
    second = MockProvider("b", text="from-b")
    result = Waterfall([first, second]).generate("hi", max_tokens=10)

    assert result.provider == "a"
    assert result.text == "from-a"
    assert first.generate_calls == 1
    assert second.generate_calls == 0


def test_failover_on_limit_error() -> None:
    reset = BASE + timedelta(hours=1)
    first = MockProvider("a", raises=ProviderLimitError("limit", reset_at=reset))
    second = MockProvider("b", text="from-b")

    result = Waterfall([first, second], clock=Clock()).generate("hi", max_tokens=10)

    assert result.provider == "b"
    assert first.generate_calls == 1  # attempted, then failed over
    assert second.generate_calls == 1


def test_failover_on_unavailable_probe_does_not_call_provider() -> None:
    first = MockProvider("a", available=False, reset_at=BASE + timedelta(hours=1))
    second = MockProvider("b", text="from-b")

    result = Waterfall([first, second]).generate("hi", max_tokens=10)

    assert result.provider == "b"
    assert first.generate_calls == 0  # skipped on probe, never dispatched


def test_all_exhausted_raises_with_earliest_reset() -> None:
    later = BASE + timedelta(hours=2)
    sooner = BASE + timedelta(hours=1)
    first = MockProvider("a", available=False, reset_at=later)
    second = MockProvider("b", available=False, reset_at=sooner)

    with pytest.raises(AllProvidersExhausted) as exc:
        Waterfall([first, second], clock=Clock()).generate("hi", max_tokens=10)

    assert exc.value.retry_at == sooner


def test_vision_routes_to_vision_capable_provider() -> None:
    text_only = MockProvider("a", supports_vision=False, text="text")
    vision = MockProvider("b", supports_vision=True, text="\\int x")

    result = Waterfall([text_only, vision]).transcribe_image(b"img")

    assert result.provider == "b"
    assert text_only.transcribe_calls == 0
    assert vision.transcribe_calls == 1


def test_vision_with_no_capable_provider_exhausts() -> None:
    text_only = MockProvider("a", supports_vision=False)

    with pytest.raises(AllProvidersExhausted) as exc:
        Waterfall([text_only]).transcribe_image(b"img")

    assert exc.value.retry_at is None  # no vision provider offered a reset


def test_vision_exhaustion_ignores_text_only_reset() -> None:
    # A text-only provider's reset must not become the wake-up for a vision call.
    text_reset = BASE + timedelta(minutes=10)
    vision_reset = BASE + timedelta(hours=2)
    text_only = MockProvider(
        "a", supports_vision=False, available=False, reset_at=text_reset
    )
    vision = MockProvider(
        "b", supports_vision=True, available=False, reset_at=vision_reset
    )

    with pytest.raises(AllProvidersExhausted) as exc:
        Waterfall([text_only, vision], clock=Clock()).transcribe_image(b"img")

    assert exc.value.retry_at == vision_reset


def test_limited_provider_cools_then_recovers_after_reset() -> None:
    clock = Clock()
    reset = BASE + timedelta(minutes=30)
    first = MockProvider("a", raises=ProviderLimitError("limit", reset_at=reset))
    second = MockProvider("b", text="from-b")
    waterfall = Waterfall([first, second], clock=clock)

    # 1st call: a hits its limit, cools until reset; b serves.
    assert waterfall.generate("x", max_tokens=10).provider == "b"
    assert first.generate_calls == 1

    # a is now healthy, but still cooling — must be skipped while now < reset.
    first.raises = None
    first.text = "from-a"
    assert waterfall.generate("x", max_tokens=10).provider == "b"
    assert first.generate_calls == 1  # not retried
    assert second.generate_calls == 2

    # After the reset window, a is cheapest-first again.
    clock.advance(timedelta(minutes=31))
    result = waterfall.generate("x", max_tokens=10)
    assert result.provider == "a"
    assert first.generate_calls == 2


def test_exponential_backoff_on_flaky_provider() -> None:
    clock = Clock()
    flaky = MockProvider("a", raises=ProviderUnavailableError("boom"))
    fallback = MockProvider("b", text="from-b")
    waterfall = Waterfall(
        [flaky, fallback], clock=clock, backoff_base=timedelta(minutes=1)
    )

    waterfall.generate("x", max_tokens=10)
    rt = waterfall._runtime["a"]
    assert rt.consecutive_failures == 1
    assert rt.cooldown_until == BASE + timedelta(minutes=1)

    # Retry after the first backoff; it fails again → delay doubles (1m → 2m).
    clock.advance(timedelta(minutes=1))
    waterfall.generate("x", max_tokens=10)
    rt = waterfall._runtime["a"]
    assert rt.consecutive_failures == 2
    assert rt.cooldown_until == BASE + timedelta(minutes=3)  # now(+1m) + 2m


def test_backoff_capped() -> None:
    clock = Clock()
    flaky = MockProvider("a", raises=ProviderUnavailableError("boom"))
    fallback = MockProvider("b", text="from-b")
    waterfall = Waterfall(
        [flaky, fallback],
        clock=clock,
        backoff_base=timedelta(minutes=1),
        backoff_cap=timedelta(minutes=4),
    )

    for _ in range(6):  # delays would be 1,2,4,8,... but cap at 4m
        waterfall.generate("x", max_tokens=10)
        clock.advance(timedelta(hours=1))  # always past cooldown

    delay = waterfall._runtime["a"].cooldown_until - clock.now + timedelta(hours=1)
    assert delay <= timedelta(minutes=4)


def test_success_clears_backoff_state() -> None:
    clock = Clock()
    flaky = MockProvider("a", raises=ProviderUnavailableError("boom"))
    fallback = MockProvider("b", text="from-b")
    waterfall = Waterfall(
        [flaky, fallback], clock=clock, backoff_base=timedelta(minutes=1)
    )

    waterfall.generate("x", max_tokens=10)  # a fails, backs off
    assert waterfall._runtime["a"].consecutive_failures == 1

    clock.advance(timedelta(minutes=2))  # past cooldown
    flaky.raises = None  # a is healthy again
    flaky.text = "from-a"
    result = waterfall.generate("x", max_tokens=10)

    assert result.provider == "a"
    assert waterfall._runtime["a"].consecutive_failures == 0
    assert waterfall._runtime["a"].cooldown_until is None


def test_disabled_provider_is_skipped() -> None:
    disabled = MockProvider("a", enabled=False, text="from-a")
    enabled = MockProvider("b", text="from-b")

    result = Waterfall([disabled, enabled]).generate("x", max_tokens=10)

    assert result.provider == "b"
    assert disabled.generate_calls == 0


def test_only_disabled_provider_exhausts_without_retry() -> None:
    # The hard "never spend" case: paid disabled and nothing else has headroom.
    paid = MockProvider("paid", enabled=False, available=True)

    with pytest.raises(AllProvidersExhausted) as exc:
        Waterfall([paid]).generate("x", max_tokens=10)

    assert exc.value.retry_at is None
