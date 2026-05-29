"""Gemini free-tier provider — the cheapest-first default.

Stub: carries real static metadata (vision-capable, $0) but is not yet wired to
the SDK. The multi-axis budget probe (requests/min + requests/day + tokens) and
the generate/transcribe calls land in Phase 7. Until then it probes as
unconfigured so the waterfall skips it cleanly.
"""

from __future__ import annotations

from backend.services.providers.base import (
    BudgetProbe,
    Provider,
    ProviderResult,
    ProviderUnavailableError,
)

_NOT_IMPLEMENTED = "gemini provider not yet implemented (Phase 7)"


class GeminiProvider(Provider):
    name = "gemini_free"
    supports_vision = True

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def budget_probe(self) -> BudgetProbe:
        return BudgetProbe(
            available=False,
            headroom=0,
            binding_axis="unconfigured" if not self.configured else "rpm",
            reset_at=None,
            supports_vision=self.supports_vision,
        )

    def generate(self, prompt: str, *, max_tokens: int) -> ProviderResult:
        raise ProviderUnavailableError(_NOT_IMPLEMENTED)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        raise ProviderUnavailableError(_NOT_IMPLEMENTED)
