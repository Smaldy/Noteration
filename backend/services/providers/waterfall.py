"""Cheapest-first provider waterfall with failover and single-wake-up backoff.

Walks providers in cost order; the first with headroom takes the call. On a
limit-hit it cools that provider (until its ``reset_at``) and moves on; on a
hard error it applies exponential backoff. When every enabled provider is
exhausted it raises ``AllProvidersExhausted`` carrying the earliest reset time,
so the queue can schedule one wake-up instead of spinning (see docs/architecture.md).

The waterfall never sleeps — time is injected via ``clock`` so behavior is
deterministic and the queue owns the actual waiting.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from backend.services.providers.base import (
    AllProvidersExhausted,
    ImagePart,
    Provider,
    ProviderLimitError,
    ProviderResult,
    ProviderUnavailableError,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class _ProviderRuntime:
    """Mutable failover state tracked per provider, keyed by name."""

    cooldown_until: datetime | None = None
    consecutive_failures: int = 0


@dataclass
class Waterfall:
    """Orders providers cheapest-first and routes calls with failover."""

    providers: list[Provider]
    clock: Callable[[], datetime] = _utcnow
    backoff_base: timedelta = timedelta(minutes=1)
    backoff_cap: timedelta = timedelta(hours=1)
    _runtime: dict[str, _ProviderRuntime] = field(default_factory=dict)

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        response_schema: dict | None = None,
        images: list[ImagePart] | None = None,
    ) -> ProviderResult:
        # Images make this a vision dispatch, so the walk skips text-only
        # providers instead of failing over into one that would reject them.
        return self._dispatch(
            lambda p: p.generate(
                prompt,
                max_tokens=max_tokens,
                response_schema=response_schema,
                images=images,
            ),
            need_vision=bool(images),
        )

    def transcribe_image(
        self, image: bytes, *, max_tokens: int = 1024, prompt: str | None = None
    ) -> ProviderResult:
        return self._dispatch(
            lambda p: p.transcribe_image(image, max_tokens=max_tokens, prompt=prompt),
            need_vision=True,
        )

    # -- internals -----------------------------------------------------------

    def _runtime_for(self, provider: Provider) -> _ProviderRuntime:
        return self._runtime.setdefault(provider.name, _ProviderRuntime())

    def _candidates(self, now: datetime, *, need_vision: bool) -> list[Provider]:
        """Enabled, non-cooling providers in cost order (vision-capable if needed)."""
        candidates = []
        for provider in self.providers:
            if not provider.enabled:
                continue
            if need_vision and not provider.supports_vision:
                continue
            rt = self._runtime_for(provider)
            if rt.cooldown_until is not None and rt.cooldown_until > now:
                continue
            candidates.append(provider)
        return candidates

    def _dispatch(
        self,
        call: Callable[[Provider], ProviderResult],
        *,
        need_vision: bool,
    ) -> ProviderResult:
        now = self.clock()
        wake_candidates: list[datetime] = []
        last_error: str | None = None  # surfaced via AllProvidersExhausted.reason

        # Cooling providers that could serve *this* call still contribute their
        # reset time to the wake-up calculation (a text-only provider's reset is
        # irrelevant to a vision dispatch, so it must not pull the wake earlier).
        for provider in self.providers:
            if not provider.enabled:
                continue
            if need_vision and not provider.supports_vision:
                continue
            rt = self._runtime_for(provider)
            if rt.cooldown_until is not None and rt.cooldown_until > now:
                wake_candidates.append(rt.cooldown_until)

        for provider in self._candidates(now, need_vision=need_vision):
            probe = provider.budget_probe()
            if need_vision and not probe.supports_vision:
                continue
            if not probe.available or probe.headroom <= 0:
                if probe.reset_at is not None:
                    wake_candidates.append(probe.reset_at)
                continue

            try:
                result = call(provider)
            except ProviderLimitError as exc:
                until = exc.reset_at or (now + self.backoff_base)
                self._cool(provider, until)
                wake_candidates.append(until)
                last_error = f"{provider.name}: {exc}"
                continue
            except ProviderUnavailableError as exc:
                until = self._backoff(provider, now)
                wake_candidates.append(until)
                last_error = f"{provider.name}: {exc}"
                continue

            self._record_success(provider)
            return result

        retry_at = min(wake_candidates) if wake_candidates else None
        raise AllProvidersExhausted(retry_at=retry_at, reason=last_error)

    def _cool(self, provider: Provider, until: datetime) -> None:
        """Cool a limited provider until its window reopens."""
        rt = self._runtime_for(provider)
        rt.cooldown_until = until

    def _backoff(self, provider: Provider, now: datetime) -> datetime:
        """Apply exponential backoff to a flaky provider; return its retry time."""
        rt = self._runtime_for(provider)
        rt.consecutive_failures += 1
        delay = self.backoff_base * (2 ** (rt.consecutive_failures - 1))
        delay = min(delay, self.backoff_cap)
        rt.cooldown_until = now + delay
        return rt.cooldown_until

    def _record_success(self, provider: Provider) -> None:
        """Clear failover state after a successful call."""
        rt = self._runtime_for(provider)
        rt.cooldown_until = None
        rt.consecutive_failures = 0
