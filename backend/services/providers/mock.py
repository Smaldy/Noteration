"""Configurable in-memory provider for testing the waterfall and queue.

Lives in the package (not tests/) so Phase 4's queue tests can reuse it.
"""

from __future__ import annotations

from datetime import datetime

from backend.services.providers.base import (
    BudgetProbe,
    Provider,
    ProviderResult,
)


class MockProvider(Provider):
    """A provider whose probe and call behavior are fully controllable.

    - ``available`` / ``headroom`` / ``reset_at`` shape ``budget_probe()``.
    - ``raises`` (if set) is raised from generate/transcribe to simulate a
      mid-call limit or hard failure; otherwise a deterministic result is
      returned. Call counts are recorded for assertions.
    """

    def __init__(
        self,
        name: str,
        *,
        supports_vision: bool = False,
        enabled: bool = True,
        available: bool = True,
        headroom: int = 100,
        binding_axis: str = "none",
        reset_at: datetime | None = None,
        raises: Exception | None = None,
        text: str = "ok",
        cost: float = 0.0,
    ) -> None:
        self.name = name
        self.supports_vision = supports_vision
        self.enabled = enabled
        self.available = available
        self.headroom = headroom
        self.binding_axis = binding_axis
        self.reset_at = reset_at
        self.raises = raises
        self.text = text
        self.cost = cost
        self.generate_calls = 0
        self.transcribe_calls = 0

    def budget_probe(self) -> BudgetProbe:
        return BudgetProbe(
            available=self.available,
            headroom=self.headroom,
            binding_axis=self.binding_axis,
            reset_at=self.reset_at,
            supports_vision=self.supports_vision,
        )

    def generate(self, prompt: str, *, max_tokens: int) -> ProviderResult:
        self.generate_calls += 1
        if self.raises is not None:
            raise self.raises
        return ProviderResult(text=self.text, provider=self.name, cost=self.cost)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        self.transcribe_calls += 1
        if self.raises is not None:
            raise self.raises
        return ProviderResult(text=self.text, provider=self.name, cost=self.cost)
