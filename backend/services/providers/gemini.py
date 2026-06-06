"""Gemini free-tier provider — the cheapest-first default ($0, vision-capable).

Wired to the ``google-genai`` SDK (lazily imported so the package loads without
it). Budget is modelled locally (requests/min + requests/day) since the free tier
exposes no remaining-quota API. The SDK client and clock are injectable so the
request/response/error logic is testable without network. See cost-strategy.md.

**Model rotation.** The free tier's request-per-day (RPD) limit is *per model* but
the daily *token* budget is shared across all Gemini models. So this provider can
hold several models at once: on a per-model RPD limit (a 429 on one model) it
rotates to the next model internally; only when *every* model it holds is limited
(the shared token budget hit, which 429s them all) does it report
``ProviderLimitError`` to the waterfall — which then falls through to Ollama. A
single-model provider (rotation disabled) simply holds one model. See
``docs/cost-strategy.md`` and the Settings ``gemini_rotation`` toggle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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

# The Gemini models the app offers. flash-lite tiers are cheapest and spend no
# output-token budget on "thinking"; the full flash tiers are more capable, newer
# generations stronger still. These are the exact API model-id strings passed to
# ``generate_content`` — a wrong id 404s, so they're verified against ListModels
# (the plain ``gemini-3.1-flash`` id is NOT served — only ``-flash-lite`` is, and
# ``gemini-3.5-flash`` is the newest full flash). Single source of truth.
GEMINI_2_5_FLASH_LITE = "gemini-2.5-flash-lite"
GEMINI_2_5_FLASH = "gemini-2.5-flash"
GEMINI_3_1_FLASH_LITE = "gemini-3.1-flash-lite"
GEMINI_3_5_FLASH = "gemini-3.5-flash"

# Models a user may pin when rotation is OFF (Settings.gemini_model).
SELECTABLE_MODELS: tuple[str, ...] = (
    GEMINI_2_5_FLASH_LITE,
    GEMINI_2_5_FLASH,
    GEMINI_3_1_FLASH_LITE,
    GEMINI_3_5_FLASH,
)
# Order tried when rotation is ON: best quality first, rotating to the next model
# only when the current one hits its per-model RPD limit.
ROTATION_ORDER: tuple[str, ...] = (
    GEMINI_3_5_FLASH,
    GEMINI_3_1_FLASH_LITE,
    GEMINI_2_5_FLASH,
    GEMINI_2_5_FLASH_LITE,
)
# Audio transcription uses this one model only (no rotation, no Ollama fallback —
# Ollama can't transcribe audio). See services/transcription.py. Uses the newest
# full flash (gemini-3.5-flash), verified via ListModels to accept audio and return
# a complete transcript.
TRANSCRIBE_MODEL = GEMINI_3_5_FLASH
# Generous output cap for a full lecture transcript (a ~1h lecture is ~12k tokens).
TRANSCRIBE_MAX_TOKENS = 32768
# Seconds to wait for an uploaded audio file to leave PROCESSING before giving up.
_FILE_ACTIVE_TIMEOUT = 120.0

# Default single model (rotation OFF). flash-lite is the cheapest 2.5 tier and,
# unlike gemini-2.5-flash, spends no output-token budget on "thinking".
DEFAULT_MODEL = GEMINI_2_5_FLASH_LITE

# When a 429 carries no explicit reset time, cool that model for this long before
# re-trying it. Long enough that an RPD-exhausted model isn't hammered (rotation
# covers the gap via the other models); short enough that the queue re-checks
# within the hour in case it was a transient per-minute blip.
_DEFAULT_LIMIT_COOLDOWN = timedelta(hours=1)

_VISION_PROMPT = (
    "Transcribe the equation in this image to LaTeX. Output only the LaTeX, "
    "with no surrounding text or delimiters."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _file_state(file: Any) -> str:
    """Normalize a Files-API file's state to its enum NAME (e.g. 'ACTIVE')."""
    state = getattr(file, "state", None)
    if state is None:
        return "ACTIVE"  # no state field → treat as ready
    return str(getattr(state, "name", state)).upper()


@dataclass
class _ModelSlot:
    """One Gemini model with its own per-model RPD/RPM budget tracker.

    ``cooldown_until`` records a real 429 (which the local limiter can't predict):
    a limited model is skipped until then so rotation moves to the next model.
    """

    model: str
    limiter: FreeTierLimiter
    cooldown_until: datetime | None = None


class GeminiProvider(Provider):
    name = "gemini_free"
    supports_vision = True

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        models: list[str] | None = None,
        enabled: bool = True,
        client: Any | None = None,
        clock: Callable[[], datetime] = _utcnow,
        rpm: int = DEFAULT_RPM,
        rpd: int = DEFAULT_RPD,
    ) -> None:
        # ``models`` (rotation) wins; otherwise a single ``model`` (or the default).
        if models:
            model_list = list(models)
        else:
            model_list = [model or DEFAULT_MODEL]
        self.api_key = api_key
        self.enabled = enabled
        self._client = client
        self.clock = clock
        self._slots: list[_ModelSlot] = [
            _ModelSlot(name, FreeTierLimiter(rpm=rpm, rpd=rpd)) for name in model_list
        ]

    @property
    def models(self) -> list[str]:
        return [slot.model for slot in self._slots]

    @property
    def model(self) -> str:
        """The primary (first) model — back-compat for single-model callers."""
        return self._slots[0].model

    @property
    def configured(self) -> bool:
        return self._client is not None or bool(self.api_key)

    def budget_probe(self) -> BudgetProbe:
        if not self.configured:
            return BudgetProbe(False, 0, "unconfigured", None, self.supports_vision)
        now = self.clock()
        resets: list[datetime] = []
        for slot in self._slots:
            if slot.cooldown_until is not None and slot.cooldown_until > now:
                resets.append(slot.cooldown_until)
                continue
            snap = slot.limiter.snapshot(now)
            if snap.available and snap.headroom > 0:
                # First model with headroom serves; report its binding axis.
                return BudgetProbe(
                    True, snap.headroom, snap.binding_axis, None, self.supports_vision
                )
            if snap.reset_at is not None:
                resets.append(snap.reset_at)
        reset_at = min(resets) if resets else None
        return BudgetProbe(False, 0, "rpd", reset_at, self.supports_vision)

    def generate(
        self,
        prompt: str,
        *,
        max_tokens: int,
        response_schema: dict[str, Any] | None = None,
    ) -> ProviderResult:
        config = self._config(max_tokens, response_schema=response_schema)
        return self._dispatch(
            lambda client, model: client.models.generate_content(
                model=model, contents=prompt, config=config
            )
        )

    def transcribe_image(
        self, image: bytes, *, max_tokens: int = 1024, prompt: str | None = None
    ) -> ProviderResult:
        from google.genai import types  # lazy

        contents = [
            types.Part.from_bytes(data=image, mime_type="image/png"),
            prompt or _VISION_PROMPT,
        ]
        config = self._config(max_tokens)
        return self._dispatch(
            lambda client, model: client.models.generate_content(
                model=model, contents=contents, config=config
            )
        )

    def transcribe_audio(
        self,
        audio_path: str,
        *,
        mime_type: str,
        prompt: str,
        max_tokens: int = TRANSCRIBE_MAX_TOKENS,
    ) -> ProviderResult:
        """Transcribe an audio file to text via the Files API (no rotation).

        Built for a single fixed model (``TRANSCRIBE_MODEL``) — transcription does
        not rotate and has no Ollama fallback (Ollama can't hear audio), so on a
        limit this raises ``ProviderLimitError`` and the caller surfaces a
        "try again later" message. Large lecture files exceed the inline request
        cap, so the audio is uploaded via the Files API and referenced by handle.
        """
        import time as _time

        from google.genai import types  # lazy

        client = self._get_client()
        slot = self._slots[0]
        try:
            uploaded = client.files.upload(
                file=audio_path,
                config=types.UploadFileConfig(mime_type=mime_type),
            )
            # Audio is processed server-side before it can be referenced; wait for
            # it to leave PROCESSING (usually quick).
            deadline = _time.monotonic() + _FILE_ACTIVE_TIMEOUT
            while _file_state(uploaded) == "PROCESSING":
                if _time.monotonic() > deadline:
                    raise ProviderUnavailableError("audio file processing timed out")
                _time.sleep(1.0)
                uploaded = client.files.get(name=uploaded.name)
            if _file_state(uploaded) == "FAILED":
                raise ProviderUnavailableError("audio file processing failed")
            response = client.models.generate_content(
                model=slot.model,
                contents=[uploaded, prompt],
                config=self._config(max_tokens),
            )
        except Exception as exc:  # noqa: BLE001 - mapped to typed provider errors
            raise self._map_error(exc) from exc
        slot.limiter.record(self.clock())
        return self._to_result(response)

    # -- internals -----------------------------------------------------------

    def _dispatch(
        self, call: Callable[[Any, str], Any]
    ) -> ProviderResult:
        """Run ``call`` against the first model with headroom, rotating on limits.

        Per-model RPD limit (a 429 on one model) → cool that model, try the next.
        All models limited (shared token budget exhausted) → raise
        ``ProviderLimitError`` so the waterfall falls through to Ollama. A hard
        (non-limit) error propagates immediately so the waterfall backs off the
        whole provider rather than retrying the same fault on every model.

        The model cooldown and the *raised* reset time are **decoupled**: a 429
        with no explicit reset cools that model for ``_DEFAULT_LIMIT_COOLDOWN``
        (so it isn't hammered) but the error carries ``reset_at=None``, so the
        queue defers the affected job only briefly and can re-route it to Ollama
        on the next cycle instead of stranding it until Gemini's window reopens.
        Only a *known* reset (a real limiter window) is propagated as the job's
        defer time.
        """
        client = self._get_client()
        now = self.clock()
        serve_again_at: list[datetime] = []  # only real "Gemini serves again" times
        last_limit: str | None = None

        for slot in self._slots:
            if slot.cooldown_until is not None and slot.cooldown_until > now:
                continue  # cooling (maybe a default) — don't let it set the defer
            snap = slot.limiter.snapshot(now)
            if not (snap.available and snap.headroom > 0):
                if snap.reset_at is not None:
                    serve_again_at.append(snap.reset_at)
                continue
            try:
                response = call(client, slot.model)
            except Exception as exc:  # noqa: BLE001 - mapped to typed provider errors
                mapped = self._map_error(exc)
                if isinstance(mapped, ProviderLimitError):
                    slot.cooldown_until = mapped.reset_at or (
                        now + _DEFAULT_LIMIT_COOLDOWN
                    )
                    if mapped.reset_at is not None:
                        serve_again_at.append(mapped.reset_at)
                    last_limit = str(exc)
                    continue
                raise mapped from exc
            slot.limiter.record(now)
            return self._to_result(response)

        reset_at = min(serve_again_at) if serve_again_at else None
        raise ProviderLimitError(
            last_limit or "all Gemini models are rate-limited", reset_at=reset_at
        )

    def _config(
        self, max_tokens: int, *, response_schema: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Generation config with "thinking" disabled.

        The flash models otherwise spend much of ``max_output_tokens`` on hidden
        reasoning, which truncates notes and the assessment JSON. We want the whole
        budget on visible content; flash-lite has no thinking anyway, so disabling
        it is uniform and safe across the offered models.

        When ``response_schema`` is given, Gemini's native **structured output** is
        engaged (``response_mime_type="application/json"`` + the schema), so the
        consolidated generation stage gets one validated JSON object back.
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
            or "rate limit" in lowered
            or "ratelimit" in lowered
        ):
            return ProviderLimitError(message)  # reset unknown → waterfall backoff
        return ProviderUnavailableError(message)
