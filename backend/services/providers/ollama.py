"""Ollama local provider — $0, benchmark-gated, hardware-bound.

Wired to the ``ollama`` SDK (lazily imported). When configured (a model is set),
budget is bounded only by local hardware throughput — no quota — so the probe
reports ``binding_axis="hardware"`` with no reset. ``supports_vision`` stays False
until the benchmark picks a vision-capable local model. Client is injectable so
the request/response/error logic is testable without a running Ollama.
"""

from __future__ import annotations

from typing import Any

from backend.services.providers.base import (
    BudgetProbe,
    Provider,
    ProviderResult,
    ProviderUnavailableError,
    VisionNotSupportedError,
)

DEFAULT_HOST = "http://localhost:11434"
# Local throughput headroom is effectively unbounded vs. a single dispatch.
_HARDWARE_HEADROOM = 1 << 30


class OllamaProvider(Provider):
    name = "ollama"
    supports_vision = False

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        model: str | None = None,
        enabled: bool = False,  # opt-in; off until benchmark-gated (cost-strategy.md)
        client: Any | None = None,
    ) -> None:
        self.host = host
        self.model = model
        self.enabled = enabled
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.model)

    def budget_probe(self) -> BudgetProbe:
        if not self.configured:
            return BudgetProbe(False, 0, "unconfigured", None, self.supports_vision)
        # Local model: always available (no quota), bounded only by hardware.
        return BudgetProbe(True, _HARDWARE_HEADROOM, "hardware", None, self.supports_vision)

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        response_schema: dict[str, Any] | None = None,
    ) -> ProviderResult:
        # Ollama supports structured output via ``format`` (a JSON Schema). Pass
        # the schema through when present so a local model also returns one JSON
        # object for the consolidated generation stage.
        return self._call(prompt, max_tokens, images=None, fmt=response_schema)

    def transcribe_image(self, image: bytes, *, max_tokens: int = 1024) -> ProviderResult:
        if not self.supports_vision:
            raise VisionNotSupportedError("ollama model is not vision-capable")
        return self._call(
            "Transcribe the equation in this image to LaTeX. Output only LaTeX.",
            max_tokens,
            images=[image],
        )

    # -- internals -----------------------------------------------------------

    def _call(
        self,
        prompt: str,
        max_tokens: int,
        *,
        images: list[bytes] | None,
        fmt: dict[str, Any] | None = None,
    ) -> ProviderResult:
        try:
            client = self._get_client()
            kwargs: dict[str, Any] = {
                "model": self.model,
                "prompt": prompt,
                "options": {"num_predict": max_tokens},
            }
            if images is not None:
                kwargs["images"] = images
            if fmt is not None:
                kwargs["format"] = fmt
            response = client.generate(**kwargs)
        except Exception as exc:  # noqa: BLE001 - mapped to a typed provider error
            raise ProviderUnavailableError(str(exc)) from exc
        return self._to_result(response)

    def _get_client(self) -> Any:
        if self._client is None:
            import ollama  # lazy

            self._client = ollama.Client(host=self.host)
        return self._client

    def _to_result(self, response: Any) -> ProviderResult:
        # The SDK returns a mapping-like / pydantic object; support both accesses.
        return ProviderResult(
            text=_field(response, "response", "") or "",
            provider=self.name,
            input_tokens=_field(response, "prompt_eval_count", 0) or 0,
            output_tokens=_field(response, "eval_count", 0) or 0,
            cost=0.0,  # local, $0
        )


def _field(response: Any, key: str, default: Any) -> Any:
    try:
        return response[key]
    except (KeyError, TypeError, IndexError):
        return getattr(response, key, default)
