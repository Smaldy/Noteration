"""Assemble the provider waterfall from configuration.

Cheapest-first by default (gemini → ollama → claude); ``allow_paid`` gates the
paid tier (the hard "never spend" switch), ``provider_order`` can override the
order, and Ollama joins only when enabled with a chosen model (benchmark-gated).
Pure construction — no network — so it is unit-testable.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from backend.services.providers.base import Provider
from backend.services.providers.claude import ClaudeProvider
from backend.services.providers.gemini import GeminiProvider
from backend.services.providers.ollama import DEFAULT_HOST, OllamaProvider
from backend.services.providers.waterfall import Waterfall

if TYPE_CHECKING:
    from backend.models.settings import Settings

DEFAULT_ORDER = ("gemini_free", "ollama", "claude_paid")


def build_waterfall(
    *,
    gemini_key: str | None = None,
    claude_key: str | None = None,
    allow_paid: bool = False,
    ollama_model: str | None = None,
    ollama_host: str = DEFAULT_HOST,
    ollama_enabled: bool = False,
    provider_order: list[str] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Waterfall:
    """Build a configured ``Waterfall`` cheapest-first (or per ``provider_order``)."""
    clock_kwargs = {"clock": clock} if clock is not None else {}
    # Coerce to bool: a transient (un-flushed) Settings row reads None for its
    # boolean columns (SQLAlchemy defaults apply only on flush), and None must
    # not leak into provider `enabled` flags.
    by_name: dict[str, Provider] = {
        "gemini_free": GeminiProvider(gemini_key, **clock_kwargs),
        "ollama": OllamaProvider(
            model=ollama_model,
            host=ollama_host,
            enabled=bool(ollama_enabled and ollama_model),
        ),
        "claude_paid": ClaudeProvider(
            claude_key, enabled=bool(allow_paid), **clock_kwargs
        ),
    }

    names = provider_order or list(DEFAULT_ORDER)
    # Honor the configured order, then append any known providers it omitted so a
    # partial override never silently drops a tier.
    ordered_names = [n for n in names if n in by_name]
    ordered_names += [n for n in DEFAULT_ORDER if n not in ordered_names]
    return Waterfall([by_name[n] for n in ordered_names])


def build_waterfall_from_settings(
    settings: "Settings",
    *,
    ollama_model: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Waterfall:
    """Build the waterfall from the persisted ``Settings`` singleton."""
    return build_waterfall(
        gemini_key=settings.api_key_gemini,
        claude_key=settings.api_key_claude,
        allow_paid=settings.allow_paid,
        ollama_model=ollama_model,  # model TBD by benchmark; gated by ollama_enabled
        ollama_enabled=settings.ollama_enabled,
        provider_order=settings.provider_order,
        clock=clock,
    )
