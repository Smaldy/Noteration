"""Assemble the provider waterfall from configuration.

Cheapest-first by default (gemini → ollama); ``provider_order`` can override the
order, and Ollama joins only when enabled with a chosen model. Pure construction —
no network — so it is unit-testable.

Gemini holds one model (rotation OFF → ``gemini_model``) or all four (rotation ON →
``ROTATION_ORDER``); the per-model RPD rotation and shared-token fall-through to
Ollama live inside ``GeminiProvider``. ``gemini_enabled=False`` disables the whole
Gemini tier (e.g. to test Ollama's note quality) so the waterfall skips it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from backend.services.local_ai.runtime import resolve_ollama_model
from backend.services.providers.base import Provider
from backend.services.providers.gemini import DEFAULT_MODEL as GEMINI_DEFAULT_MODEL
from backend.services.providers.gemini import ROTATION_ORDER, GeminiProvider
from backend.services.providers.ollama import DEFAULT_HOST, OllamaProvider
from backend.services.providers.waterfall import Waterfall

if TYPE_CHECKING:
    from backend.models.settings import Settings

DEFAULT_ORDER = ("gemini_free", "ollama")


def build_waterfall(
    *,
    gemini_key: str | None = None,
    gemini_model: str | None = None,
    gemini_enabled: bool = True,
    gemini_rotation: bool = False,
    ollama_model: str | None = None,
    ollama_host: str = DEFAULT_HOST,
    ollama_enabled: bool = False,
    provider_order: list[str] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Waterfall:
    """Build a configured ``Waterfall`` cheapest-first (or per ``provider_order``)."""
    clock_kwargs = {"clock": clock} if clock is not None else {}
    # Rotation ON → hold every free-tier model in order; OFF → just the pinned one.
    gemini_models = (
        list(ROTATION_ORDER)
        if gemini_rotation
        else [gemini_model or GEMINI_DEFAULT_MODEL]
    )
    # Coerce to bool: a transient (un-flushed) Settings row reads None for its
    # boolean columns (SQLAlchemy defaults apply only on flush), and None must
    # not leak into provider `enabled` flags.
    by_name: dict[str, Provider] = {
        "gemini_free": GeminiProvider(
            gemini_key,
            models=gemini_models,
            enabled=bool(gemini_enabled),
            **clock_kwargs,
        ),
        "ollama": OllamaProvider(
            model=ollama_model,
            host=ollama_host,
            enabled=bool(ollama_enabled and ollama_model),
        ),
    }

    names = provider_order or list(DEFAULT_ORDER)
    # Honor the configured order, skipping names we no longer know (e.g. a stored
    # order referencing a removed provider), then append any known providers it
    # omitted so a partial override never silently drops a tier.
    ordered_names = [n for n in names if n in by_name]
    ordered_names += [n for n in DEFAULT_ORDER if n not in ordered_names]
    return Waterfall([by_name[n] for n in ordered_names])


def build_waterfall_from_settings(
    settings: Settings,
    *,
    ollama_model: str | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Waterfall:
    """Build the waterfall from the persisted ``Settings`` singleton."""
    return build_waterfall(
        gemini_key=settings.api_key_gemini,
        gemini_model=settings.gemini_model,
        # gemini_enabled defaults True; a transient Settings reads None for it.
        gemini_enabled=settings.gemini_enabled is not False,
        gemini_rotation=bool(settings.gemini_rotation),
        # An explicit arg wins; otherwise the interactive default (fast model,
        # honoring prefer_quality). Overnight lanes swap the model per claim in
        # the worker — see services/local_ai/runtime.py.
        ollama_model=ollama_model
        or resolve_ollama_model(settings, overnight=False),
        ollama_enabled=settings.ollama_enabled,
        provider_order=settings.provider_order,
        clock=clock,
    )
