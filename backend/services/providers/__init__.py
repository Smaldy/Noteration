"""Provider abstraction + cheapest-first waterfall."""

from backend.services.providers.base import (
    AllProvidersExhausted,
    BudgetProbe,
    Provider,
    ProviderError,
    ProviderLimitError,
    ProviderResult,
    ProviderUnavailableError,
    VisionNotSupportedError,
)
from backend.services.providers.factory import (
    build_waterfall,
    build_waterfall_from_settings,
)
from backend.services.providers.gemini import GeminiProvider
from backend.services.providers.mock import MockProvider
from backend.services.providers.ollama import OllamaProvider
from backend.services.providers.waterfall import Waterfall

__all__ = [
    "Provider",
    "ProviderResult",
    "BudgetProbe",
    "ProviderError",
    "ProviderLimitError",
    "ProviderUnavailableError",
    "VisionNotSupportedError",
    "AllProvidersExhausted",
    "Waterfall",
    "MockProvider",
    "GeminiProvider",
    "OllamaProvider",
    "build_waterfall",
    "build_waterfall_from_settings",
]
