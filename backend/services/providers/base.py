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
from typing import Any


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
    no provider offered a reset time (e.g. all disabled). ``reason`` carries the
    last provider error message (e.g. a 429 quota text) so the queue can record
    *why* work is paused instead of deferring silently.
    """

    def __init__(
        self, *, retry_at: datetime | None = None, reason: str | None = None
    ) -> None:
        super().__init__(reason or "all providers exhausted")
        self.retry_at = retry_at
        self.reason = reason


class Provider(ABC):
    """One AI backend behind a uniform interface.

    Subclasses set ``name`` and ``supports_vision``. ``enabled`` can be flipped
    off (e.g. the Gemini tier's master switch disables it wholesale).
    """

    name: str = "provider"
    supports_vision: bool = False
    enabled: bool = True
    # Per-provider HTTP request timeout (seconds). Local providers need a generous
    # value: on a long prompt a local model's time-to-first-token can be 5-10s, and
    # default HTTP client timeouts (often a few seconds) would drop a valid
    # in-flight request as if it had failed. ``None`` means "use the client/SDK
    # default". Ollama overrides this to 120s; remote SDK providers (Gemini)
    # rely on their SDK's own timeout handling.
    request_timeout: float | None = None

    @abstractmethod
    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        response_schema: dict[str, Any] | None = None,
    ) -> ProviderResult:
        """Produce text for a prompt, capped at ``max_tokens`` output.

        When ``response_schema`` (a JSON Schema dict) is given, the provider is
        asked to return a single JSON object matching it — used by the
        consolidated generation stage to get notes + assessment in one turn.
        Providers without native structured-output support fall back to relying
        on the prompt's JSON instruction; ``ProviderResult.text`` is still the
        raw (JSON) string in every case.
        """

    @abstractmethod
    def transcribe_image(
        self, image: bytes, *, max_tokens: int = 1024, prompt: str | None = None
    ) -> ProviderResult:
        """Transcribe/analyze an image and return its text output.

        Defaults to the provider's built-in equation→LaTeX instruction. ``prompt``
        overrides it so the same vision path can serve other structured tasks (the
        Exercise Duplicator's per-page exercise extraction asks for a JSON array).
        """

    @abstractmethod
    def budget_probe(self) -> BudgetProbe:
        """Report current headroom without spending quota."""
