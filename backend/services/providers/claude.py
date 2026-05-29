"""Paid Claude provider — last resort in the waterfall.

Stub. Real budget probe models the rolling 5-hour token window + reset
timestamp; ``generate``/``transcribe_image`` and cost accounting land in Phase 7.
Disable via ``enabled=False`` for the hard "never spend" switch.
"""

from __future__ import annotations

from backend.services.providers.base import (
    BudgetProbe,
    Provider,
    ProviderResult,
    ProviderUnavailableError,
)

_NOT_IMPLEMENTED = "claude provider not yet implemented (Phase 7)"


class ClaudeProvider(Provider):
    name = "claude_paid"
    supports_vision = True

    def __init__(self, api_key: str | None = None, *, enabled: bool = True) -> None:
        self.api_key = api_key
        self.enabled = enabled

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def budget_probe(self) -> BudgetProbe:
        return BudgetProbe(
            available=False,
            headroom=0,
            binding_axis="unconfigured" if not self.configured else "tokens",
            reset_at=None,
            supports_vision=self.supports_vision,
        )

    def generate(self, prompt: str, *, max_tokens: int) -> ProviderResult:
        raise ProviderUnavailableError(_NOT_IMPLEMENTED)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        raise ProviderUnavailableError(_NOT_IMPLEMENTED)
