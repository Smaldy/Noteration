"""Ollama local provider — $0, benchmark-gated, hardware-bound.

Wired to the ``ollama`` SDK (lazily imported). When configured (a model is set),
budget is bounded only by local hardware throughput — no quota — so the probe
reports ``binding_axis="hardware"`` with no reset. ``supports_vision`` stays False
until the benchmark picks a vision-capable local model. Client is injectable so
the request/response/error logic is testable without a running Ollama.

Hardened for sustained overnight runs on the 3060-laptop baseline (docs/architecture.md):
an inter-request cooldown, a generous request timeout, locked sampling params for
benchmark reproducibility, and VRAM pinning so the model isn't cold-reloaded
between topics. See the per-attribute comments below.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import Any

from backend.services.providers.base import (
    BudgetProbe,
    Provider,
    ProviderResult,
    ProviderUnavailableError,
    VisionNotSupportedError,
)

DEFAULT_HOST = "http://localhost:11434"
# Inter-request cooldown after a successful local call (seconds). Spacing calls
# keeps a 6GB 3060 laptop from thermal-throttling across a long/overnight run and
# smooths sustained throughput. Overridable via OLLAMA_COOLDOWN_SECONDS.
DEFAULT_COOLDOWN_SECONDS = 3.0
# Generous HTTP timeout: local TTFT can be 5-10s on long prompts, and default HTTP
# timeouts would drop a valid in-flight request. See Provider.request_timeout.
DEFAULT_REQUEST_TIMEOUT = 120.0
# VRAM pinning. Without this Ollama evicts the model after its keepalive timeout
# (default 5 min), forcing a cold-load penalty at the start of each topic during
# an overnight run. -1 keeps the model resident indefinitely. Override via
# OLLAMA_KEEP_ALIVE (an int seconds, -1, or a duration string like "10m").
DEFAULT_KEEP_ALIVE: int | str = -1
# Locked sampling params. The benchmark and overnight runs MUST use identical
# params or their results aren't comparable, so these are hard-coded unless a
# caller explicitly overrides them at construction time.
DEFAULT_TEMPERATURE = 0.2
DEFAULT_TOP_P = 0.9
# Local throughput headroom is effectively unbounded vs. a single dispatch.
_HARDWARE_HEADROOM = 1 << 30


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_keep_alive() -> int | str:
    raw = os.environ.get("OLLAMA_KEEP_ALIVE")
    if raw is None or not raw.strip():
        return DEFAULT_KEEP_ALIVE
    raw = raw.strip()
    try:
        return int(raw)  # seconds, or -1
    except ValueError:
        return raw  # a duration string Ollama understands, e.g. "10m"


class OllamaProvider(Provider):
    name = "ollama"
    supports_vision = False

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        model: str | None = None,
        enabled: bool = False,  # opt-in; off until benchmark-gated (docs/architecture.md)
        client: Any | None = None,
        cooldown_seconds: float | None = None,
        request_timeout: float | None = None,
        keep_alive: int | str | None = None,
        temperature: float = DEFAULT_TEMPERATURE,
        top_p: float = DEFAULT_TOP_P,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.host = host
        self.model = model
        self.enabled = enabled
        self._client = client
        # An explicit constructor value wins; otherwise fall back to the env
        # override, then the documented default.
        self.cooldown_seconds = (
            cooldown_seconds
            if cooldown_seconds is not None
            else _env_float("OLLAMA_COOLDOWN_SECONDS", DEFAULT_COOLDOWN_SECONDS)
        )
        self.request_timeout = (
            request_timeout if request_timeout is not None else DEFAULT_REQUEST_TIMEOUT
        )
        self.keep_alive = keep_alive if keep_alive is not None else _env_keep_alive()
        self.temperature = temperature
        self.top_p = top_p
        self._sleep = sleep

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

    def transcribe_image(
        self, image: bytes, *, max_tokens: int = 1024, prompt: str | None = None
    ) -> ProviderResult:
        if not self.supports_vision:
            raise VisionNotSupportedError("ollama model is not vision-capable")
        return self._call(
            prompt
            or "Transcribe the equation in this image to LaTeX. Output only LaTeX.",
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
                "options": {
                    "num_predict": max_tokens,
                    # Locked for reproducibility (see DEFAULT_TEMPERATURE/TOP_P).
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                },
                # VRAM pinning on every request body (see DEFAULT_KEEP_ALIVE).
                "keep_alive": self.keep_alive,
            }
            if images is not None:
                kwargs["images"] = images
            if fmt is not None:
                kwargs["format"] = fmt
            response = client.generate(**kwargs)
        except Exception as exc:  # noqa: BLE001 - mapped to a typed provider error
            # Fail fast on error — do NOT cool down; the queue owns retry/backoff.
            raise ProviderUnavailableError(str(exc)) from exc
        result = self._to_result(response)
        # Inter-request cooldown AFTER a successful call only. This runs in
        # production (and in the benchmark) so measured throughput reflects real
        # sustained behavior, not burst speed.
        if self.cooldown_seconds > 0:
            self._sleep(self.cooldown_seconds)
        return result

    def _get_client(self) -> Any:
        if self._client is None:
            import ollama  # lazy

            self._client = ollama.Client(host=self.host, timeout=self.request_timeout)
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
