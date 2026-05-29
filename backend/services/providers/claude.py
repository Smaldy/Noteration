"""Paid Claude provider — last resort in the waterfall.

Wired to the ``anthropic`` SDK (lazily imported). Budget is modelled as a rolling
token window (the ~5-hour usage window); cost is accrued per token. Disable via
``enabled=False`` for the hard "never spend" switch. Client and clock are
injectable so the request/response/cost/error logic is testable without network.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from backend.services.providers.base import (
    BudgetProbe,
    Provider,
    ProviderLimitError,
    ProviderResult,
    ProviderUnavailableError,
)
from backend.services.providers.budget import RollingTokenWindow

DEFAULT_MODEL = "claude-sonnet-4-6"
# Default pricing (USD per token) — Sonnet-class; override as prices change.
DEFAULT_INPUT_PRICE = 3.0 / 1_000_000
DEFAULT_OUTPUT_PRICE = 15.0 / 1_000_000
# Conservative rolling-window token budget; tune to the account's real window.
DEFAULT_WINDOW_TOKENS = 1_000_000
_VISION_PROMPT = (
    "Transcribe the equation in this image to LaTeX. Output only the LaTeX, "
    "with no surrounding text or delimiters."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClaudeProvider(Provider):
    name = "claude_paid"
    supports_vision = True

    def __init__(
        self,
        api_key: str | None = None,
        *,
        enabled: bool = True,
        model: str = DEFAULT_MODEL,
        client: Any | None = None,
        clock: Callable[[], datetime] = _utcnow,
        window_tokens: int = DEFAULT_WINDOW_TOKENS,
        input_price: float = DEFAULT_INPUT_PRICE,
        output_price: float = DEFAULT_OUTPUT_PRICE,
    ) -> None:
        self.api_key = api_key
        self.enabled = enabled
        self.model = model
        self._client = client
        self.clock = clock
        self.input_price = input_price
        self.output_price = output_price
        self.window = RollingTokenWindow(limit_tokens=window_tokens)

    @property
    def configured(self) -> bool:
        return self._client is not None or bool(self.api_key)

    def budget_probe(self) -> BudgetProbe:
        if not self.configured:
            return BudgetProbe(False, 0, "unconfigured", None, self.supports_vision)
        snap = self.window.snapshot(self.clock())
        return BudgetProbe(
            snap.available, snap.headroom, "tokens", snap.reset_at, self.supports_vision
        )

    def generate(self, prompt: str, *, max_tokens: int) -> ProviderResult:
        content = [{"type": "text", "text": prompt}]
        return self._call(content, max_tokens)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(image).decode("ascii"),
                },
            },
            {"type": "text", "text": _VISION_PROMPT},
        ]
        return self._call(content, max_tokens)

    # -- internals -----------------------------------------------------------

    def _call(self, content: list[dict[str, Any]], max_tokens: int) -> ProviderResult:
        try:
            client = self._get_client()
            message = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": content}],
            )
        except Exception as exc:  # noqa: BLE001 - mapped to typed provider errors
            raise self._map_error(exc) from exc
        return self._to_result(message)

    def _get_client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise ProviderUnavailableError("claude not configured")
            import anthropic  # lazy

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _to_result(self, message: Any) -> ProviderResult:
        text = "".join(
            getattr(block, "text", "") for block in getattr(message, "content", [])
        )
        usage = getattr(message, "usage", None)
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        cost = input_tokens * self.input_price + output_tokens * self.output_price
        self.window.record(self.clock(), input_tokens + output_tokens)
        return ProviderResult(
            text=text,
            provider=self.name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )

    def _map_error(self, exc: Exception) -> Exception:
        if isinstance(exc, ProviderUnavailableError):
            return exc
        name = type(exc).__name__
        message = str(exc)
        if name == "RateLimitError" or "429" in message or "rate_limit" in message.lower():
            return ProviderLimitError(message)
        return ProviderUnavailableError(message)
