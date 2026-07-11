"""Stage 3 speed estimation — table lookup, fallbacks, and catalog size math."""

from backend.services.local_ai.bandwidth import (
    FALLBACK_GBPS,
    bandwidth_for_profile,
    estimate_tok_per_sec,
    lookup_bandwidth_gbps,
)
from backend.services.local_ai.catalog import MODELS, Q4_K_M, kv_bytes_per_token
from backend.services.local_ai.hardware import (
    ComputeBackend,
    Confidence,
    GraphicsClass,
    HardwareProfile,
)

GB = 1024**3


def make_profile(
    *,
    gpu_vendor=None,
    gpu_name=None,
    vram=None,
    ram=16 * GB,
    graphics_class=GraphicsClass.cpu_only,
    backend=ComputeBackend.cpu,
    usable=8 * GB,
) -> HardwareProfile:
    return HardwareProfile(
        os_name="linux",
        arch="x86_64",
        ram_bytes=ram,
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        vram_bytes=vram,
        graphics_class=graphics_class,
        backend=backend,
        usable_memory_bytes=usable,
        eligible_quants=("Q4_K_M",),
        confidence=Confidence.high,
    )


def test_laptop_variant_beats_desktop_substring():
    """Longest-key matching must hit the mobile entry, not the desktop one."""
    assert lookup_bandwidth_gbps("NVIDIA GeForce RTX 3060 Laptop GPU") == 336
    assert lookup_bandwidth_gbps("NVIDIA GeForce RTX 3060") == 360
    assert lookup_bandwidth_gbps("NVIDIA GeForce RTX 4090 Laptop GPU") == 576
    assert lookup_bandwidth_gbps("NVIDIA GeForce RTX 4090") == 1008


def test_apple_chip_tiers_match_longest_first():
    assert lookup_bandwidth_gbps("Apple M2 Pro") == 200
    assert lookup_bandwidth_gbps("Apple M2") == 100
    assert lookup_bandwidth_gbps("Apple M4 Max") == 410


def test_unknown_gpu_returns_none():
    assert lookup_bandwidth_gbps("Some Future GPU 9999") is None
    assert lookup_bandwidth_gbps(None) is None


def test_profile_bandwidth_paths():
    table = make_profile(
        gpu_vendor="nvidia",
        gpu_name="NVIDIA GeForce RTX 3060 Laptop GPU",
        graphics_class=GraphicsClass.dedicated,
        backend=ComputeBackend.cuda,
    )
    assert bandwidth_for_profile(table) == (336.0, "table")

    # AMD sized via sysfs has no marketing name: dedicated-class fallback.
    unnamed_amd = make_profile(
        gpu_vendor="amd",
        graphics_class=GraphicsClass.dedicated,
        backend=ComputeBackend.rocm,
    )
    assert bandwidth_for_profile(unnamed_amd) == (
        float(FALLBACK_GBPS["dedicated"]),
        "class-fallback",
    )

    unknown_apple = make_profile(
        gpu_vendor="apple",
        graphics_class=GraphicsClass.integrated,
        backend=ComputeBackend.metal,
    )
    assert bandwidth_for_profile(unknown_apple) == (
        float(FALLBACK_GBPS["apple"]),
        "class-fallback",
    )

    cpu = make_profile()
    assert bandwidth_for_profile(cpu) == (float(FALLBACK_GBPS["cpu"]), "cpu-fallback")


def test_cpu_backend_never_uses_the_table():
    """A name match means nothing if inference actually runs on the CPU."""
    profile = make_profile(gpu_name="NVIDIA GeForce RTX 4090")
    assert bandwidth_for_profile(profile) == (
        float(FALLBACK_GBPS["cpu"]),
        "cpu-fallback",
    )


def test_estimator_formula():
    # 336 GB/s over a 3.28 GB model at 0.55 efficiency ≈ 56 tok/s.
    assert abs(estimate_tok_per_sec(3.28e9, 336.0) - 56.3) < 0.5
    assert estimate_tok_per_sec(0, 336.0) == 0.0


def test_derived_sizes_match_published_ollama_tags():
    """params × effective-bytes-per-param must track the real Q4_K_M tag sizes."""
    published_gb = {
        "qwen3:8b": 5.2,
        "phi4": 9.1,
        "gemma3:27b": 17.0,
        "qwen3:32b": 20.0,
        "mistral-small3.2": 15.0,
    }
    by_tag = {m.tag: m for m in MODELS}
    for tag, expected_gb in published_gb.items():
        derived = by_tag[tag].size_bytes(Q4_K_M) / 1e9
        assert abs(derived - expected_gb) / expected_gb < 0.08, tag


def test_moe_reads_only_the_active_slice():
    moe = next(m for m in MODELS if m.tag == "qwen3:30b-a3b")
    assert moe.bytes_read_per_token(Q4_K_M) < moe.size_bytes(Q4_K_M) / 5


def test_kv_heuristic_tracks_known_architectures_conservatively():
    # llama3.1-8B ≈ 131 KB/token: close on the small end...
    assert 110_000 < kv_bytes_per_token(8.0) < 160_000
    # ...and over-estimating (never under) on the large end (32B ≈ 262 KB).
    assert kv_bytes_per_token(32.8) > 262_000
