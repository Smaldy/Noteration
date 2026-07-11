"""Bundled candidate-model catalog for the local AI selection (Stage 2 input).

A hand-curated slice of the Ollama library, biased toward models that are
strong at structured notes/quiz generation and available as GGUF across the
size ladder (1B → 32B). Bundling beats scraping ollama.com at setup time: the
set is small, deterministic, and unit-testable, and the install stage verifies
the exact tag + true byte size against the registry before pulling anyway.

Sizes are derived, not scraped: ``params × effective bytes-per-param`` for the
quant. The effective constants are measured properties of real GGUF files
(K-quants mix precisions per layer, plus embeddings/metadata), validated
against published Ollama tag sizes — e.g. qwen3:8b Q4_K_M 5.2 GB, phi4 9.1 GB,
gemma3:27b 17 GB, qwen3:32b 20 GB all land within ~3% of ``params × 0.62``.

``quality`` is a hand-assigned cross-family rank (bigger is better). It only
has to order candidates, not measure anything absolute; newer families
outrank older ones at equal size (the reason a plain params sort is not
enough). MoE models carry ``active_params_b`` so speed estimation charges
only the experts actually read per token, while fit still charges the full
size.
"""

from __future__ import annotations

from dataclasses import dataclass

Q4_K_M = "Q4_K_M"
Q5_K_M = "Q5_K_M"
Q6_K = "Q6_K"

# Effective on-disk bytes per parameter of real GGUF files at each quant.
EFFECTIVE_BYTES_PER_PARAM = {
    Q4_K_M: 0.62,
    Q5_K_M: 0.71,
    Q6_K: 0.82,
}

# KV-cache bytes per context token, as a function of model scale. Real values
# (fp16, GQA-era: 2 × layers × kv_heads × head_dim × 2 bytes) grow sublinearly
# with parameters because scaling adds width faster than depth: llama3.1-8B
# ≈ 131 KB/tok, qwen3-14B ≈ 164 KB/tok, 32B-class ≈ 262 KB/tok. The power fit
# below tracks the small end and over-estimates the large end, which is the
# safe direction for a fit test.
_KV_BASE_BYTES = 40_960


def kv_bytes_per_token(params_b: float) -> float:
    return _KV_BASE_BYTES * (params_b**0.6)


@dataclass(frozen=True)
class CatalogModel:
    tag: str  # Ollama library name; the install stage resolves quant tags
    display: str
    params_b: float
    quality: int  # hand-assigned cross-family rank, bigger is better
    active_params_b: float | None = None  # MoE only: params read per token

    def size_bytes(self, quant: str) -> float:
        return self.params_b * 1e9 * EFFECTIVE_BYTES_PER_PARAM[quant]

    def bytes_read_per_token(self, quant: str) -> float:
        """Dense models read every weight per token; MoE only the active slice."""
        size = self.size_bytes(quant)
        if self.active_params_b is None:
            return size
        return size * (self.active_params_b / self.params_b)


MODELS: tuple[CatalogModel, ...] = (
    CatalogModel("gemma3:1b", "Gemma 3 1B", 1.0, 10),
    CatalogModel("llama3.2:1b", "Llama 3.2 1B", 1.24, 9),
    CatalogModel("qwen3:1.7b", "Qwen 3 1.7B", 1.7, 16),
    CatalogModel("llama3.2:3b", "Llama 3.2 3B", 3.2, 20),
    CatalogModel("phi4-mini", "Phi-4 Mini 3.8B", 3.8, 24),
    CatalogModel("gemma3:4b", "Gemma 3 4B", 4.3, 26),
    CatalogModel("qwen3:4b", "Qwen 3 4B", 4.0, 28),
    CatalogModel("llama3.1:8b", "Llama 3.1 8B", 8.0, 30),
    CatalogModel("qwen3:8b", "Qwen 3 8B", 8.2, 36),
    CatalogModel("gemma3:12b", "Gemma 3 12B", 12.2, 40),
    CatalogModel("phi4", "Phi-4 14B", 14.7, 42),
    CatalogModel("qwen3:14b", "Qwen 3 14B", 14.8, 44),
    CatalogModel("qwen3:30b-a3b", "Qwen 3 30B MoE", 30.5, 46, active_params_b=3.3),
    CatalogModel("mistral-small3.2", "Mistral Small 3.2 24B", 24.0, 47),
    CatalogModel("gemma3:27b", "Gemma 3 27B", 27.4, 50),
    CatalogModel("qwen3:32b", "Qwen 3 32B", 32.8, 54),
)
