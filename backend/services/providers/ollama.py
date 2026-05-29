"""Ollama local provider — $0, benchmark-gated, hardware-bound.

Stub. When configured, real budget is bounded only by local hardware throughput
(no quota), so the probe will report ``binding_axis="hardware"`` and no reset.
``supports_vision`` stays False until the benchmark picks a vision-capable local
model. Absence of a running Ollama just removes it from the waterfall.
"""

from __future__ import annotations

from backend.services.providers.base import (
    BudgetProbe,
    Provider,
    ProviderResult,
    ProviderUnavailableError,
)

_NOT_IMPLEMENTED = "ollama provider not yet implemented (Phase 7)"


class OllamaProvider(Provider):
    name = "ollama"
    supports_vision = False

    def __init__(
        self,
        *,
        host: str = "http://localhost:11434",
        model: str | None = None,
        enabled: bool = False,  # opt-in; off until benchmark-gated (see cost-strategy.md)
    ) -> None:
        self.host = host
        self.model = model
        self.enabled = enabled

    @property
    def configured(self) -> bool:
        return bool(self.model)

    def budget_probe(self) -> BudgetProbe:
        return BudgetProbe(
            available=False,
            headroom=0,
            binding_axis="unconfigured" if not self.configured else "hardware",
            reset_at=None,
            supports_vision=self.supports_vision,
        )

    def generate(self, prompt: str, *, max_tokens: int) -> ProviderResult:
        raise ProviderUnavailableError(_NOT_IMPLEMENTED)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        raise ProviderUnavailableError(_NOT_IMPLEMENTED)
