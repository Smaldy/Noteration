"""Provider stub + base-type coverage.

The Gemini/Claude/Ollama stubs carry correct static metadata and behave safely
(probe unavailable, calls raise) until wired to their SDKs in Phase 7.
"""

import pytest

from backend.services.providers import (
    ClaudeProvider,
    GeminiProvider,
    OllamaProvider,
    ProviderResult,
    ProviderUnavailableError,
)


def test_provider_result_defaults() -> None:
    result = ProviderResult(text="hi", provider="x")
    assert result.cost == 0.0
    assert result.input_tokens == 0
    assert result.output_tokens == 0


def test_gemini_metadata_and_unconfigured_probe() -> None:
    gemini = GeminiProvider()
    assert gemini.name == "gemini_free"
    assert gemini.supports_vision is True
    probe = gemini.budget_probe()
    assert probe.available is False
    assert probe.binding_axis == "unconfigured"
    assert gemini.configured is False


def test_gemini_calls_raise_until_implemented() -> None:
    gemini = GeminiProvider(api_key="k")
    assert gemini.configured is True
    with pytest.raises(ProviderUnavailableError):
        gemini.generate("hi", max_tokens=10)
    with pytest.raises(ProviderUnavailableError):
        gemini.transcribe_image(b"img")


def test_claude_is_paid_vision_and_hard_disableable() -> None:
    claude = ClaudeProvider(enabled=False)
    assert claude.name == "claude_paid"
    assert claude.supports_vision is True
    assert claude.enabled is False  # the hard "never spend" switch


def test_ollama_local_defaults() -> None:
    ollama = OllamaProvider()
    assert ollama.name == "ollama"
    assert ollama.supports_vision is False  # until benchmark picks a vision model
    assert ollama.enabled is False  # opt-in
    assert ollama.budget_probe().reset_at is None  # no quota window
