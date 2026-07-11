"""Which local model serves a given call (Stage 6 routing rule).

Overnight lanes are hardwired to the quality model — that is the whole point
of the two-model scheme. Interactive/foreground work defaults to the fast
model, with ``ollama_prefer_quality`` as the user's "slower but higher
quality" toggle. The legacy ``ollama_model`` field acts as a manual override
base so pre-setup installs keep working unchanged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models.settings import Settings


def resolve_ollama_model(settings: Settings, *, overnight: bool) -> str | None:
    """The Ollama tag to serve this call with, or None when nothing is set."""
    fast = (
        settings.ollama_fast_model
        or settings.ollama_model
        or settings.ollama_quality_model
    )
    quality = settings.ollama_quality_model or fast
    if overnight or settings.ollama_prefer_quality:
        return quality
    return fast
