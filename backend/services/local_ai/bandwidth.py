"""Stage 3 — speed estimation from a static bandwidth table (no network).

Token generation on a memory-bound machine is dominated by reading the model
weights once per token, so:

    tok/s ≈ (memory bandwidth ÷ bytes read per token) × efficiency

``EFFICIENCY`` covers everything the pure bandwidth ceiling ignores (compute,
kv-cache reads, kernel overhead); real llama.cpp runs land at roughly half of
the theoretical ceiling, and the constant is calibrated against the dev
baseline (RTX 3060 Laptop). The estimate only has to gate a pass/fail speed
floor (Stage 4), so ±20% error is acceptable.

``GPU_BANDWIDTH_GBPS`` values are the vendors' published memory-bandwidth
specs in GB/s (bus width × effective memory clock — public facts, compiled by
hand from spec sheets; no third-party code or data files). Matching is
longest-key-first substring over the detected GPU name, so laptop keys must be
listed explicitly: mobile parts move far fewer bytes than their desktop
namesakes (a 4090 Laptop has ~57% of the desktop 4090's bandwidth) and would
otherwise match the desktop entry.

GPUs not in the table fall back to a conservative per-class constant, so an
unknown GPU degrades the estimate, never the flow. AMD on Linux is sized via
sysfs (no marketing name available), so it usually takes the dedicated-class
fallback. Intel Arc is deliberately absent: Ollama's support for it is not
solid, and detection classes Intel as shared-memory/CPU, which underestimates
Arc rather than promising speed it may not deliver.
"""

from __future__ import annotations

from backend.services.local_ai.hardware import (
    ComputeBackend,
    GraphicsClass,
    HardwareProfile,
)

EFFICIENCY = 0.55

GPU_BANDWIDTH_GBPS = {
    # NVIDIA GeForce desktop
    "5090": 1792, "5080": 960, "5070 ti": 896, "5070": 672,
    "5060 ti": 448, "5060": 448,
    "4090": 1008, "4080 super": 736, "4080": 717, "4070 ti super": 672,
    "4070 ti": 504, "4070 super": 504, "4070": 504, "4060 ti": 288, "4060": 272,
    "3090 ti": 1008, "3090": 936, "3080 ti": 912, "3080": 760,
    "3070 ti": 608, "3070": 448, "3060 ti": 448, "3060": 360, "3050": 224,
    "2080 ti": 616, "2080 super": 496, "2080": 448, "2070 super": 448,
    "2070": 448, "2060 super": 448, "2060": 336,
    "1660 super": 336, "1660 ti": 288, "1660": 192, "1650 super": 192, "1650": 128,
    "1080 ti": 484, "1080": 320, "1070 ti": 256, "1070": 256, "1060": 192, "1050": 112,
    # NVIDIA GeForce laptop (NVML names them "... Laptop GPU")
    "5090 laptop": 896, "5080 laptop": 896, "5070 ti laptop": 672, "5070 laptop": 448,
    "4090 laptop": 576, "4080 laptop": 432, "4070 laptop": 256,
    "4060 laptop": 256, "4050 laptop": 192,
    "3080 ti laptop": 512, "3080 laptop": 448, "3070 ti laptop": 448,
    "3070 laptop": 448, "3060 laptop": 336, "3050 ti laptop": 192, "3050 laptop": 192,
    # NVIDIA datacenter/workstation (common in homelabs)
    "h200": 4800, "h100": 2039, "a100": 1555, "l40s": 864, "l40": 864,
    "l4": 300, "a10": 600, "t4": 320, "v100": 897,
    "rtx a6000": 768, "rtx a5000": 768, "rtx a4000": 448,
    # AMD Radeon (windows registry names carry these; linux sysfs has no name)
    "9070 xt": 640, "9070": 640, "9060 xt": 320,
    "7900 xtx": 960, "7900 xt": 800, "7900 gre": 576, "7800 xt": 624,
    "7700 xt": 432, "7600": 288,
    "6950 xt": 576, "6900 xt": 512, "6800 xt": 512, "6800": 512,
    "6750 xt": 432, "6700 xt": 384, "6650 xt": 280, "6600 xt": 256, "6600": 224,
    "5700 xt": 448, "5700": 448, "5600 xt": 288, "5500 xt": 224,
    "vega 64": 484, "vega 56": 410, "rx 580": 256, "rx 570": 224,
    # Apple Silicon unified memory, keyed off the sysctl brand string
    # ("Apple M2 Pro"). Where a chip ships multiple bandwidth bins (M3 Max,
    # M4 Max), the lower bin is listed — conservative beats optimistic here.
    "m1 ultra": 800, "m1 max": 400, "m1 pro": 200, "m1": 68,
    "m2 ultra": 800, "m2 max": 400, "m2 pro": 200, "m2": 100,
    "m3 ultra": 800, "m3 max": 300, "m3 pro": 150, "m3": 100,
    "m4 max": 410, "m4 pro": 273, "m4": 120,
    "m5": 153,
}

_KEYS_LONGEST_FIRST = sorted(GPU_BANDWIDTH_GBPS, key=len, reverse=True)

# Conservative GB/s when the GPU isn't in the table. dedicated ≈ a mid-range
# GDDR6 card; apple ≈ a base M-chip (named chips take the table path);
# integrated/cpu ≈ dual-channel DDR4/DDR5 system memory.
FALLBACK_GBPS = {
    "dedicated": 224,
    "apple": 100,
    "integrated": 60,
    "cpu": 50,
}


def lookup_bandwidth_gbps(gpu_name: str | None) -> int | None:
    """Table bandwidth for a detected GPU name, or None when not listed."""
    if not gpu_name:
        return None
    name = gpu_name.lower()
    for key in _KEYS_LONGEST_FIRST:
        if key in name:
            return GPU_BANDWIDTH_GBPS[key]
    return None


def bandwidth_for_profile(profile: HardwareProfile) -> tuple[float, str]:
    """Effective memory bandwidth (GB/s) for a profile plus how it was chosen.

    Only a GPU-capable backend may use the table: a name match means nothing
    if inference will actually run on the CPU. Returns ``(gbps, source)``
    where source is ``"table"``, ``"class-fallback"``, or ``"cpu-fallback"``.
    """
    if profile.backend in (ComputeBackend.cuda, ComputeBackend.rocm, ComputeBackend.metal):
        from_table = lookup_bandwidth_gbps(profile.gpu_name)
        if from_table is not None:
            return float(from_table), "table"
        if profile.gpu_vendor == "apple":
            return float(FALLBACK_GBPS["apple"]), "class-fallback"
        if profile.graphics_class is GraphicsClass.dedicated:
            return float(FALLBACK_GBPS["dedicated"]), "class-fallback"
        return float(FALLBACK_GBPS["integrated"]), "class-fallback"
    return float(FALLBACK_GBPS["cpu"]), "cpu-fallback"


def estimate_tok_per_sec(bytes_read_per_token: float, bandwidth_gbps: float) -> float:
    """The Stage 3 formula. ``bytes_read_per_token`` is the quantized model
    size for a dense model, or the active-experts slice for a MoE."""
    if bytes_read_per_token <= 0:
        return 0.0
    return (bandwidth_gbps * 1e9 / bytes_read_per_token) * EFFICIENCY
