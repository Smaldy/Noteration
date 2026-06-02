"""Gemini free-tier provider — the cheapest-first default ($0, vision-capable).

Wired to the ``google-genai`` SDK (lazily imported so the package loads without
it). Budget is modelled locally (requests/min + requests/day) since the free tier
exposes no remaining-quota API. The SDK client and clock are injectable so the
request/response/error logic is testable without network. See cost-strategy.md.
"""

from __future__ import annotations

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
from backend.services.providers.budget import FreeTierLimiter

# Conservative free-tier defaults; tune as Google's quotas change.
DEFAULT_RPM = 15
DEFAULT_RPD = 1500
# gemini-2.0-flash's free tier is now limit:0 (every call 429s); 2.5 is the
# current free-tier model. flash-lite is the cheapest 2.5 tier and, unlike
# gemini-2.5-flash, spends no output-token budget on "thinking" — so it returns
# full notes/JSON within max_output_tokens instead of being truncated.
DEFAULT_MODEL = "gemini-2.5-flash-lite"
_VISION_PROMPT = (
    "Transcribe the equation in this image to LaTeX. Output only the LaTeX, "
    "with no surrounding text or delimiters."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class GeminiProvider(Provider):
    name = "gemini_free"
    supports_vision = True

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = DEFAULT_MODEL,
        client: Any | None = None,
        clock: Callable[[], datetime] = _utcnow,
        rpm: int = DEFAULT_RPM,
        rpd: int = DEFAULT_RPD,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self._client = client
        self.clock = clock
        self.limiter = FreeTierLimiter(rpm=rpm, rpd=rpd)

    @property
    def configured(self) -> bool:
        return self._client is not None or bool(self.api_key)

    def budget_probe(self) -> BudgetProbe:
        if not self.configured:
            return BudgetProbe(False, 0, "unconfigured", None, self.supports_vision)
        snap = self.limiter.snapshot(self.clock())
        return BudgetProbe(
            snap.available,
            snap.headroom,
            snap.binding_axis,
            snap.reset_at,
            self.supports_vision,
        )

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        response_schema: dict[str, Any] | None = None,
    ) -> ProviderResult:
        try:
            client = self._get_client()
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._config(max_tokens, response_schema=response_schema),
            )
        except Exception as exc:  # noqa: BLE001 - mapped to typed provider errors
            raise self._map_error(exc) from exc
        self.limiter.record(self.clock())
        return self._to_result(response)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        try:
            client = self._get_client()
            from google.genai import types  # lazy

            response = client.models.generate_content(
                model=self.model,
                contents=[
                    types.Part.from_bytes(data=image, mime_type="image/png"),
                    _VISION_PROMPT,
                ],
                config=self._config(max_tokens),
            )
        except Exception as exc:  # noqa: BLE001
            raise self._map_error(exc) from exc
        self.limiter.record(self.clock())
        return self._to_result(response)

    # -- internals -----------------------------------------------------------

    def _config(
        self, max_tokens: int, *, response_schema: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Generation config with "thinking" disabled.

        The 2.5 flash models otherwise spend much of ``max_output_tokens`` on
        hidden reasoning, which truncates notes and the assessment JSON. We want
        the whole budget on visible content; flash-lite has no thinking anyway,
        so disabling it is uniform and safe across the offered models.

        When ``response_schema`` is given, Gemini's native **structured output**
        is engaged (``response_mime_type="application/json"`` + the schema), so
        the consolidated generation stage gets one validated JSON object back —
        no second call to keep notes and assessment aligned.
        """
        from google.genai import types  # lazy

        config: dict[str, Any] = {
            "max_output_tokens": max_tokens,
            "thinking_config": types.ThinkingConfig(thinking_budget=0),
        }
        if response_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = response_schema
        return config

    def _get_client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise ProviderUnavailableError("gemini not configured")
            from google import genai  # lazy

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def _to_result(self, response: Any) -> ProviderResult:
        text = getattr(response, "text", None) or ""
        usage = getattr(response, "usage_metadata", None)
        return ProviderResult(
            text=text,
            provider=self.name,
            input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            cost=0.0,  # free tier
        )

    def _map_error(self, exc: Exception) -> Exception:
        if isinstance(exc, ProviderUnavailableError):
            return exc
        message = str(exc)
        lowered = message.lower()
        if (
            "429" in message
            or "resource_exhausted" in lowered
            or "quota" in lowered
            or "rate" in lowered
        ):
            return ProviderLimitError(message)  # reset unknown → waterfall backoff
        return ProviderUnavailableError(message)
