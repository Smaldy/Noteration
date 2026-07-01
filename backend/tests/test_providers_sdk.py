"""Real-provider wiring tests (Phase 7d).

Network is never touched: each provider takes an injected fake client, and time
is injected so budget probes are deterministic. Covers request/response parsing,
cost/usage accounting, error mapping, budget tracking, and the waterfall factory.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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

T0 = datetime(2026, 1, 1, tzinfo=UTC)


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


def test_gemini_generate_engages_structured_output() -> None:
    resp = SimpleNamespace(text="{}", usage_metadata=None)
    captured: dict = {}

    def generate_content(**kwargs):
        captured.update(kwargs)
        return resp

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    provider = GeminiProvider(client=client, clock=lambda: T0)
    schema = {"type": "object", "properties": {"notes_md": {"type": "string"}}}
    provider.generate("p", max_tokens=64, response_schema=schema)

    config = captured["config"]
    assert config["response_mime_type"] == "application/json"
    assert config["response_schema"] is schema
    # A plain call must NOT request JSON mode.
    provider.generate("p", max_tokens=64)
    assert "response_schema" not in captured["config"]


# --- Gemini model rotation --------------------------------------------------


def _gemini_per_model_client(behavior):
    """A client whose ``generate_content`` dispatches on the ``model`` kwarg.

    ``behavior`` maps model name → either an exception to raise or a response to
    return. Each call is appended to the returned ``calls`` list.
    """
    calls: list[str] = []

    def generate_content(*, model, **_kwargs):
        calls.append(model)
        outcome = behavior[model]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client = SimpleNamespace(
        models=SimpleNamespace(generate_content=generate_content)
    )
    return client, calls


def test_gemini_rotates_to_next_model_on_per_model_limit() -> None:
    ok = SimpleNamespace(text="ok", usage_metadata=None)
    client, calls = _gemini_per_model_client(
        {"m1": Exception("429 RESOURCE_EXHAUSTED"), "m2": ok}
    )
    provider = GeminiProvider(client=client, clock=lambda: T0, models=["m1", "m2"])
    result = provider.generate("p", max_tokens=10)
    assert result.text == "ok"
    # m1 hit its per-model RPD limit → rotated to m2 within the one provider.
    assert calls == ["m1", "m2"]


def test_gemini_all_models_limited_raises_limit_error() -> None:
    # When every model 429s (the shared token budget), the provider reports a
    # limit so the waterfall falls through to the next tier (Ollama).
    client, _ = _gemini_per_model_client(
        {"m1": Exception("429 quota"), "m2": Exception("429 quota")}
    )
    provider = GeminiProvider(client=client, clock=lambda: T0, models=["m1", "m2"])
    with pytest.raises(ProviderLimitError):
        provider.generate("p", max_tokens=10)


def test_gemini_unknown_limit_defers_briefly_but_cools_model() -> None:
    # A 429 with no parsed reset must NOT strand the job on Gemini's window: the
    # raised error carries reset_at=None (queue defers briefly → re-routes to
    # Ollama), while the model itself stays cooled so it isn't hammered.
    client, _ = _gemini_per_model_client(
        {"m1": Exception("429 RESOURCE_EXHAUSTED")}
    )
    provider = GeminiProvider(client=client, clock=lambda: T0, models=["m1"])
    with pytest.raises(ProviderLimitError) as excinfo:
        provider.generate("p", max_tokens=10)
    assert excinfo.value.reset_at is None  # job won't be stranded for an hour
    # …but the model is cooled, so the provider reports unavailable now.
    assert provider.budget_probe().available is False


def test_gemini_cooled_model_skipped_on_next_call() -> None:
    ok = SimpleNamespace(text="ok", usage_metadata=None)
    client, calls = _gemini_per_model_client(
        {"m1": Exception("429"), "m2": ok}
    )
    provider = GeminiProvider(client=client, clock=lambda: T0, models=["m1", "m2"])
    provider.generate("p", max_tokens=10)  # m1 limited → cooled, m2 serves
    provider.generate("p", max_tokens=10)  # m1 still cooling → straight to m2
    assert calls == ["m1", "m2", "m2"]
    # A still-usable model keeps the provider available overall.
    assert provider.budget_probe().available is True


def test_gemini_hard_error_propagates_without_rotation() -> None:
    # A non-limit (hard) error isn't model-specific — fail the provider so the
    # waterfall backs it off instead of retrying the same fault on every model.
    client, calls = _gemini_per_model_client(
        {"m1": Exception("boom"), "m2": SimpleNamespace(text="x", usage_metadata=None)}
    )
    provider = GeminiProvider(client=client, clock=lambda: T0, models=["m1", "m2"])
    with pytest.raises(ProviderUnavailableError):
        provider.generate("p", max_tokens=10)
    assert calls == ["m1"]  # did not rotate past the hard error


class _ServerError(Exception):
    """Mimics google-genai ServerError: carries an HTTP ``code`` attribute."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def test_gemini_rotates_to_next_model_on_transient_overload() -> None:
    # The delivered-app bug: model rotation tried gemini-3.5-flash first, Google
    # answered 503 "high demand", and the *whole* Gemini tier failed with a 503 to
    # the user. A transient server fault must rotate to a healthy model instead.
    ok = SimpleNamespace(text="ok", usage_metadata=None)
    client, calls = _gemini_per_model_client(
        {"m1": _ServerError(503, "model is overloaded, please try again later"), "m2": ok}
    )
    provider = GeminiProvider(client=client, clock=lambda: T0, models=["m1", "m2"])
    result = provider.generate("p", max_tokens=10)
    assert result.text == "ok"
    assert calls == ["m1", "m2"]  # rotated past the busy model


def test_gemini_rotates_on_timeout_message_without_status_code() -> None:
    # A bare timeout (httpx ReadTimeout) has no HTTP status — classify by message.
    ok = SimpleNamespace(text="ok", usage_metadata=None)
    client, calls = _gemini_per_model_client(
        {"m1": Exception("The read operation timed out"), "m2": ok}
    )
    provider = GeminiProvider(client=client, clock=lambda: T0, models=["m1", "m2"])
    assert provider.generate("p", max_tokens=10).text == "ok"
    assert calls == ["m1", "m2"]


def test_gemini_all_models_transient_defers_briefly_not_hard_fail() -> None:
    # If every model is transiently busy, report a *limit* (brief defer + re-route),
    # NOT ProviderUnavailableError (which would back the whole tier off for minutes).
    client, _ = _gemini_per_model_client(
        {"m1": _ServerError(503, "high demand"), "m2": _ServerError(500, "internal error")}
    )
    provider = GeminiProvider(client=client, clock=lambda: T0, models=["m1", "m2"])
    with pytest.raises(ProviderLimitError) as excinfo:
        provider.generate("p", max_tokens=10)
    assert excinfo.value.reset_at is None  # job retries soon, not stranded for an hour


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
    # cooldown_seconds=0 so this parsing unit test doesn't incur the real 3s sleep.
    provider = OllamaProvider(model="llama3", client=_ollama_client(response), cooldown_seconds=0)
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


# --- Ollama hardening (Wave A) ---------------------------------------------


def test_ollama_cooldown_fires_after_success() -> None:
    slept: list[float] = []
    provider = OllamaProvider(
        model="llama3",
        client=_ollama_client({"response": "ok"}),
        cooldown_seconds=2.5,
        sleep=slept.append,
    )
    provider.generate("p", max_tokens=10)
    assert slept == [2.5]  # cooldown fired once with the configured value


def test_ollama_no_cooldown_on_error() -> None:
    slept: list[float] = []
    provider = OllamaProvider(
        model="llama3",
        client=_ollama_client(raises=Exception("down")),
        cooldown_seconds=3.0,
        sleep=slept.append,
    )
    with pytest.raises(ProviderUnavailableError):
        provider.generate("p", max_tokens=10)
    assert slept == []  # fail fast — never sleep on error


def test_ollama_cooldown_default_three_seconds() -> None:
    slept: list[float] = []
    provider = OllamaProvider(
        model="llama3", client=_ollama_client({"response": "ok"}), sleep=slept.append
    )
    provider.generate("p", max_tokens=10)
    assert slept == [3.0]  # default cooldown


def test_ollama_cooldown_env_override(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_COOLDOWN_SECONDS", "7")
    slept: list[float] = []
    provider = OllamaProvider(
        model="llama3", client=_ollama_client({"response": "ok"}), sleep=slept.append
    )
    provider.generate("p", max_tokens=10)
    assert slept == [7.0]


def test_ollama_client_initializes_with_120s_timeout(monkeypatch) -> None:
    import ollama

    captured: dict = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return _ollama_client({"response": "ok"})

    monkeypatch.setattr(ollama, "Client", fake_client)
    # No injected client → _get_client builds one with the request timeout.
    provider = OllamaProvider(model="llama3", cooldown_seconds=0)
    provider.generate("p", max_tokens=10)
    assert captured["timeout"] == 120.0


def test_ollama_keep_alive_in_every_call_type() -> None:
    captured: list[dict] = []

    def generate(**kwargs):
        captured.append(kwargs)
        return {"response": "ok"}

    client = SimpleNamespace(generate=generate)
    provider = OllamaProvider(model="llava", client=client, cooldown_seconds=0)
    provider.supports_vision = True  # vision-capable local model
    provider.generate("p", max_tokens=10)
    provider.transcribe_image(b"img", max_tokens=10)

    assert len(captured) == 2
    assert all(call["keep_alive"] == -1 for call in captured)


def test_ollama_keep_alive_env_override(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_KEEP_ALIVE", "600")
    captured: dict = {}

    def generate(**kwargs):
        captured.update(kwargs)
        return {"response": "ok"}

    provider = OllamaProvider(
        model="llama3", client=SimpleNamespace(generate=generate), cooldown_seconds=0
    )
    provider.generate("p", max_tokens=10)
    assert captured["keep_alive"] == 600


def test_ollama_temperature_locked() -> None:
    captured: dict = {}

    def generate(**kwargs):
        captured.update(kwargs)
        return {"response": "ok"}

    provider = OllamaProvider(
        model="llama3", client=SimpleNamespace(generate=generate), cooldown_seconds=0
    )
    provider.generate("p", max_tokens=10)
    assert captured["options"]["temperature"] == 0.2
    assert captured["options"]["top_p"] == 0.9


# --- factory ----------------------------------------------------------------


def test_factory_default_order_and_paid_gate() -> None:
    settings = Settings(api_key_gemini="g", api_key_claude="c", allow_paid=False)
    waterfall = build_waterfall_from_settings(settings)
    names = [p.name for p in waterfall.providers]
    assert names == ["gemini_free", "ollama", "claude_paid"]
    claude = waterfall.providers[-1]
    assert claude.enabled is False  # never-spend by default


def test_factory_default_settings_yield_bool_flags() -> None:
    # A transient Settings has None boolean columns; flags must coerce to bool.
    waterfall = build_waterfall_from_settings(Settings())
    by_name = {p.name: p for p in waterfall.providers}
    assert by_name["claude_paid"].enabled is False
    assert by_name["ollama"].enabled is False


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


def test_factory_rotation_holds_all_four_models() -> None:
    from backend.services.providers.gemini import ROTATION_ORDER

    settings = Settings(api_key_gemini="g", gemini_rotation=True)
    waterfall = build_waterfall_from_settings(settings)
    gemini = next(p for p in waterfall.providers if p.name == "gemini_free")
    assert gemini.models == list(ROTATION_ORDER)


def test_factory_single_model_when_rotation_off() -> None:
    settings = Settings(api_key_gemini="g", gemini_model="gemini-3.5-flash")
    gemini = next(
        p for p in build_waterfall_from_settings(settings).providers
        if p.name == "gemini_free"
    )
    assert gemini.models == ["gemini-3.5-flash"]


def test_factory_gemini_disabled_skips_tier() -> None:
    # Disabling Gemini lets Ollama serve (test a local model's quality).
    settings = Settings(
        api_key_gemini="g",
        gemini_enabled=False,
        ollama_enabled=True,
        ollama_model="llama3.1",
    )
    by_name = {p.name: p for p in build_waterfall_from_settings(settings).providers}
    assert by_name["gemini_free"].enabled is False
    assert by_name["ollama"].enabled is True
    assert by_name["ollama"].model == "llama3.1"


def test_factory_ollama_needs_a_model() -> None:
    settings = Settings(ollama_enabled=True)  # enabled but no model
    by_name = {p.name: p for p in build_waterfall_from_settings(settings).providers}
    assert by_name["ollama"].enabled is False
