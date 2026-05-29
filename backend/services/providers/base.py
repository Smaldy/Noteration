"""Provider abstraction — the single interface every backend implements.

No code outside this package knows which model is active. The waterfall
(``waterfall.py``) tries providers cheapest-first and fails over on limits.

Key types:
- ``Provider``      — abstract interface (generate / transcribe_image / budget_probe).
- ``BudgetProbe``   — multi-axis headroom; reports the *binding* constraint.
- ``ProviderResult``— text + token/cost telemetry, stamped with the provider.
- exceptions        — drive failover and the single-wake-up backoff.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BudgetProbe:
    """A provider's current headroom, reporting the axis that binds first.

    Free tiers limit on several axes at once (requests/min, requests/day,
    tokens); modelling only one causes the classic "hit the per-minute wall
    while believing there's daily headroom" failure. ``binding_axis`` names
    whichever runs out first and ``reset_at`` is when it reopens.
    """

    available: bool  # can dispatch at least one unit right now
    headroom: int  # units that fit now per the binding axis (>= 0)
    binding_axis: str  # 'rpm' | 'rpd' | 'tokens' | 'hardware' | 'none'
    reset_at: datetime | None  # when the binding window reopens; None = no window
    supports_vision: bool


@dataclass(frozen=True)
class ProviderResult:
    """Output of a generate/transcribe call, with stamping + cost telemetry."""

    text: str
    provider: str  # which provider served it (for QueueJob.assigned_provider)
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0  # USD; 0.0 for free tiers


class ProviderError(Exception):
    """Base class for provider failures."""


class ProviderLimitError(ProviderError):
    """A budget/rate limit was hit (possibly mid-call).

    Carries ``reset_at`` so the waterfall can cool the provider and compute the
    single wake-up time when every provider is exhausted.
    """

    def __init__(self, message: str, *, reset_at: datetime | None = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


class ProviderUnavailableError(ProviderError):
    """A hard/transient failure (not configured, network error, 5xx).

    Triggers failover and exponential backoff on that provider so a flaky
    backend can't burn cycles.
    """


class VisionNotSupportedError(ProviderError):
    """A non-vision provider was asked to transcribe an image."""


class AllProvidersExhausted(ProviderError):
    """No enabled provider had headroom on this walk of the waterfall.

    ``retry_at`` is the earliest moment any provider's window reopens — the
    queue schedules a single wake-up then instead of spinning. ``None`` means
    no provider offered a reset time (e.g. all disabled).
    """

    def __init__(self, *, retry_at: datetime | None = None) -> None:
        super().__init__("all providers exhausted")
        self.retry_at = retry_at


class Provider(ABC):
    """One AI backend behind a uniform interface.

    Subclasses set ``name`` and ``supports_vision``. ``enabled`` can be flipped
    off (e.g. the hard "never spend" switch disables paid Claude).
    """

    name: str = "provider"
    supports_vision: bool = False
    enabled: bool = True

    @abstractmethod
    def generate(self, prompt: str, *, max_tokens: int) -> ProviderResult:
        """Produce text for a prompt, capped at ``max_tokens`` output."""

    @abstractmethod
    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        """Transcribe an image (e.g. a cropped equation) to text/LaTeX."""

    @abstractmethod
    def budget_probe(self) -> BudgetProbe:
        """Report current headroom without spending quota."""
