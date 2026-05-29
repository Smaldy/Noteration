"""Real-provider wiring tests (Phase 7d).

Network is never touched: each provider takes an injected fake client, and time
is injected so budget probes are deterministic. Covers request/response parsing,
cost/usage accounting, error mapping, budget tracking, and the waterfall factory.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.models.settings import Settings
from backend.services.providers.base import (
    ProviderLimitError,
    ProviderUnavailableError,
    VisionNotSupportedError,
)
from backend.services.providers.budget import FreeTierLimiter, RollingTokenWindow
from backend.services.providers.claude import ClaudeProvider
from backend.services.providers.factory import build_waterfall_from_settings
from backend.services.providers.gemini import GeminiProvider
from backend.services.providers.ollama import OllamaProvider

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


# --- budget trackers --------------------------------------------------------


def test_free_tier_limiter_binding_axis_and_reset() -> None:
    limiter = FreeTierLimiter(rpm=2, rpd=10)
    for _ in range(2):
        limiter.record(T0)
    snap = limiter.snapshot(T0)
    assert snap.available is False
    assert snap.binding_axis == "rpm"
    assert snap.reset_at == T0 + timedelta(minutes=1)
    # a minute later the per-minute window has reopened
    later = limiter.snapshot(T0 + timedelta(minutes=1, seconds=1))
    assert later.available is True


def test_free_tier_limiter_daily_binds_when_minute_ok() -> None:
    limiter = FreeTierLimiter(rpm=100, rpd=3)
    for i in range(3):
        limiter.record(T0 + timedelta(seconds=i))
    snap = limiter.snapshot(T0 + timedelta(seconds=3))
    assert snap.binding_axis == "rpd"
    assert snap.available is False


def test_rolling_token_window() -> None:
    window = RollingTokenWindow(limit_tokens=100, window=timedelta(hours=5))
    window.record(T0, 80)
    assert window.snapshot(T0).headroom == 20
    window.record(T0, 30)  # now over budget
    over = window.snapshot(T0)
    assert over.available is False
    assert over.reset_at == T0 + timedelta(hours=5)
    # after the window passes, it reopens
    assert window.snapshot(T0 + timedelta(hours=5, seconds=1)).available is True


# --- Gemini -----------------------------------------------------------------


def _gemini_client(response=None, *, raises=None):
    def generate_content(**_kwargs):
        if raises is not None:
            raise raises
        return response

    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


def test_gemini_generate_parses_and_records() -> None:
    resp = SimpleNamespace(
        text="dense notes",
        usage_metadata=SimpleNamespace(prompt_token_count=11, candidates_token_count=22),
    )
    provider = GeminiProvider(client=_gemini_client(resp), clock=lambda: T0, rpm=5, rpd=50)
    result = provider.generate("prompt", max_tokens=100)

    assert result.text == "dense notes"
    assert result.provider == "gemini_free"
    assert (result.input_tokens, result.output_tokens) == (11, 22)
    assert result.cost == 0.0
    # the call was recorded against the budget
    assert provider.budget_probe().headroom == 4


def test_gemini_maps_quota_to_limit_error() -> None:
    provider = GeminiProvider(client=_gemini_client(raises=Exception("429 RESOURCE_EXHAUSTED")))
    with pytest.raises(ProviderLimitError):
        provider.generate("p", max_tokens=10)


def test_gemini_maps_other_error_to_unavailable() -> None:
    provider = GeminiProvider(client=_gemini_client(raises=Exception("boom")))
    with pytest.raises(ProviderUnavailableError):
        provider.generate("p", max_tokens=10)


def test_gemini_unconfigured_probe() -> None:
    probe = GeminiProvider().budget_probe()
    assert probe.available is False
    assert probe.binding_axis == "unconfigured"


def test_gemini_transcribe_builds_image_request() -> None:
    resp = SimpleNamespace(text="x^2", usage_metadata=None)
    captured: dict = {}

    def generate_content(**kwargs):
        captured.update(kwargs)
        return resp

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    provider = GeminiProvider(client=client, clock=lambda: T0)
    result = provider.transcribe_image(b"\x89PNGdata", max_tokens=64)

    assert result.text == "x^2"
    assert isinstance(captured["contents"], list) and len(captured["contents"]) == 2


# --- Claude -----------------------------------------------------------------


def _claude_client(message=None, *, raises=None):
    def create(**_kwargs):
        if raises is not None:
            raise raises
        return message

    return SimpleNamespace(messages=SimpleNamespace(create=create))


def test_claude_generate_parses_cost_and_window() -> None:
    message = SimpleNamespace(
        content=[SimpleNamespace(text="answer ")],
        usage=SimpleNamespace(input_tokens=1000, output_tokens=2000),
    )
    provider = ClaudeProvider(
        client=_claude_client(message),
        clock=lambda: T0,
        input_price=3e-6,
        output_price=15e-6,
        window_tokens=10_000,
    )
    result = provider.generate("prompt", max_tokens=500)

    assert result.text == "answer "
    assert result.input_tokens == 1000 and result.output_tokens == 2000
    assert result.cost == pytest.approx(1000 * 3e-6 + 2000 * 15e-6)
    # tokens recorded against the rolling window
    assert provider.budget_probe().headroom == 10_000 - 3000


class _NamedRateLimit(Exception):
    pass


_NamedRateLimit.__name__ = "RateLimitError"


def test_claude_maps_rate_limit() -> None:
    provider = ClaudeProvider(client=_claude_client(raises=_NamedRateLimit("slow down")))
    with pytest.raises(ProviderLimitError):
        provider.generate("p", max_tokens=10)


def test_claude_disabled_for_never_spend() -> None:
    provider = ClaudeProvider("key", enabled=False)
    assert provider.enabled is False  # waterfall skips disabled providers


# --- Ollama -----------------------------------------------------------------


def _ollama_client(response=None, *, raises=None):
    def generate(**_kwargs):
        if raises is not None:
            raise raises
        return response

    return SimpleNamespace(generate=generate)


def test_ollama_generate_parses_dict_response() -> None:
    response = {"response": "local notes", "prompt_eval_count": 5, "eval_count": 9}
    provider = OllamaProvider(model="llama3", client=_ollama_client(response))
    result = provider.generate("prompt", max_tokens=100)

    assert result.text == "local notes"
    assert (result.input_tokens, result.output_tokens) == (5, 9)
    assert result.cost == 0.0


def test_ollama_probe_available_when_configured() -> None:
    probe = OllamaProvider(model="llama3").budget_probe()
    assert probe.available is True
    assert probe.binding_axis == "hardware"
    assert probe.reset_at is None
    # unconfigured (no model) is skipped
    assert OllamaProvider().budget_probe().available is False


def test_ollama_vision_rejected_by_default() -> None:
    provider = OllamaProvider(model="llama3", client=_ollama_client({"response": "x"}))
    with pytest.raises(VisionNotSupportedError):
        provider.transcribe_image(b"img")


def test_ollama_maps_errors_to_unavailable() -> None:
    provider = OllamaProvider(model="llama3", client=_ollama_client(raises=Exception("down")))
    with pytest.raises(ProviderUnavailableError):
        provider.generate("p", max_tokens=10)


# --- factory ----------------------------------------------------------------


def test_factory_default_order_and_paid_gate() -> None:
    settings = Settings(api_key_gemini="g", api_key_claude="c", allow_paid=False)
    waterfall = build_waterfall_from_settings(settings)
    names = [p.name for p in waterfall.providers]
    assert names == ["gemini_free", "ollama", "claude_paid"]
    claude = waterfall.providers[-1]
    assert claude.enabled is False  # never-spend by default


def test_factory_enables_paid_and_custom_order() -> None:
    settings = Settings(
        api_key_gemini="g",
        api_key_claude="c",
        allow_paid=True,
        provider_order=["claude_paid", "gemini_free"],
    )
    waterfall = build_waterfall_from_settings(settings)
    names = [p.name for p in waterfall.providers]
    assert names[0] == "claude_paid"
    assert "ollama" in names  # omitted tier still appended
    assert waterfall.providers[names.index("claude_paid")].enabled is True
