"""Stages 2/4/7 — golden selections for the representative-machine fixtures.

These pin the tiering behavior per machine class (Task 2): each test is a
hardware profile we can't necessarily reproduce physically, asserting the
exact (model, quant, context) the selector must produce. If a constant tweak
changes a golden outcome, that's a deliberate re-tiering and the test should
be updated consciously.
"""

from backend.services.local_ai.hardware import (
    CPU_USABLE_FRACTION,
    DEDICATED_USABLE_FRACTION,
    UNIFIED_USABLE_FRACTION,
    ComputeBackend,
    Confidence,
    GraphicsClass,
    HardwareProfile,
)
from backend.services.local_ai.selection import select_models

GB = 1024**3


def make_profile(
    *,
    usable_pool,
    fraction,
    gpu_vendor=None,
    gpu_name=None,
    vram=None,
    ram=16 * GB,
    graphics_class=GraphicsClass.cpu_only,
    backend=ComputeBackend.cpu,
    os_name="linux",
    arch="x86_64",
) -> HardwareProfile:
    return HardwareProfile(
        os_name=os_name,
        arch=arch,
        ram_bytes=ram,
        gpu_vendor=gpu_vendor,
        gpu_name=gpu_name,
        vram_bytes=vram,
        graphics_class=graphics_class,
        backend=backend,
        usable_memory_bytes=int(usable_pool * fraction),
        eligible_quants=("Q4_K_M", "Q5_K_M", "Q6_K"),
        confidence=Confidence.high,
    )


def rtx_3060_laptop() -> HardwareProfile:
    return make_profile(
        usable_pool=6 * GB,
        fraction=DEDICATED_USABLE_FRACTION,
        gpu_vendor="nvidia",
        gpu_name="NVIDIA GeForce RTX 3060 Laptop GPU",
        vram=6 * GB,
        graphics_class=GraphicsClass.dedicated,
        backend=ComputeBackend.cuda,
    )


def test_rtx_3060_laptop_splits_with_a_lightly_offloaded_8b():
    """6 GB VRAM + 16 GB RAM: the quality role may spill into system RAM, but
    it must still clear the 10 tok/s quality floor — an 8B with a light spill
    does (~14 tok/s); a 14B at ~4 tok/s does not. The fast role stays
    strictly in VRAM."""
    result = select_models(rtx_3060_laptop())
    assert result.quality.tag == "qwen3:8b"
    assert result.quality.quant == "Q4_K_M"
    assert 10 <= result.quality.est_tok_s < 20
    assert result.fast.tag == "qwen3:4b"
    assert result.fast.quant == "Q6_K"
    assert result.fast.est_tok_s >= 20
    assert not result.converged
    assert not result.weak_machine
    assert any("system memory" in m for m in result.messages)  # honest offload note


def test_rtx_4090_converges_on_the_resident_32b():
    """24 GB VRAM: the offloaded Q5 misses the quality floor, so both roles
    land on the same resident 32B Q4 — one pull, one card."""
    profile = make_profile(
        usable_pool=24 * GB,
        fraction=DEDICATED_USABLE_FRACTION,
        gpu_vendor="nvidia",
        gpu_name="NVIDIA GeForce RTX 4090",
        vram=24 * GB,
        graphics_class=GraphicsClass.dedicated,
        backend=ComputeBackend.cuda,
    )
    result = select_models(profile)
    assert result.quality.tag == "qwen3:32b"
    assert result.quality.quant == "Q4_K_M"
    assert result.quality.context == 4096  # the context-shrink lever in action
    assert result.converged
    assert result.fast.est_tok_s >= 20
    assert not result.messages


def test_m2_pro_32gb_splits_quality_and_fast():
    """Apple mid-tier still splits: the best dense model over the quality
    floor (14B Q5) for overnight, and the 30B MoE for interactive (only ~3B
    active params per token, so it flies)."""
    profile = make_profile(
        usable_pool=32 * GB,
        fraction=UNIFIED_USABLE_FRACTION,
        ram=32 * GB,
        gpu_vendor="apple",
        gpu_name="Apple M2 Pro",
        graphics_class=GraphicsClass.integrated,
        backend=ComputeBackend.metal,
        os_name="darwin",
        arch="arm64",
    )
    result = select_models(profile)
    assert result.quality.tag == "qwen3:14b"
    assert result.quality.quant == "Q5_K_M"
    assert result.quality.est_tok_s >= 10  # the 27B at ~6 tok/s misses the floor
    assert result.fast.tag == "qwen3:30b-a3b"
    assert result.fast.quant == "Q4_K_M"
    assert result.fast.est_tok_s >= 20
    assert not result.converged
    assert not result.weak_machine
    # Two distinct pulls: the total is the sum, not one model's size.
    assert result.total_download_bytes > result.quality.download_bytes


def test_cpu_only_16gb_converges_on_the_best_4b_over_the_floor():
    """CPU-only: a 12B runs ~3 tok/s and misses the quality floor, so both
    roles land on the best 4B that clears 10 tok/s, with an honest
    sluggishness message. Still local, still functional."""
    profile = make_profile(
        usable_pool=16 * GB, fraction=CPU_USABLE_FRACTION, ram=16 * GB
    )
    result = select_models(profile)
    assert result.quality.tag == "qwen3:4b"
    assert result.quality.quant == "Q4_K_M"
    assert result.converged
    assert 10 <= result.fast.est_tok_s < 20
    assert not result.weak_machine
    assert any("slow" in m for m in result.messages)


def test_m1_8gb_converges_sluggish_but_functional():
    """Entry Apple Silicon: one 4B model for both roles, under the responsive
    target but over the hard floor — flagged, not blocked."""
    profile = make_profile(
        usable_pool=8 * GB,
        fraction=UNIFIED_USABLE_FRACTION,
        ram=8 * GB,
        gpu_vendor="apple",
        gpu_name="Apple M1",
        graphics_class=GraphicsClass.integrated,
        backend=ComputeBackend.metal,
        os_name="darwin",
        arch="arm64",
    )
    result = select_models(profile)
    assert result.quality.tag == "qwen3:4b"
    assert result.quality.quant == "Q6_K"
    assert result.converged
    assert not result.weak_machine
    assert 10 <= result.fast.est_tok_s < 20
    assert any("slow" in m for m in result.messages)


def test_unnamed_amd_16gb_splits_on_the_conservative_fallback():
    """AMD sized via sysfs (no marketing name): the dedicated-class bandwidth
    fallback pairs a resident 14B overnight with a resident 8B interactive."""
    profile = make_profile(
        usable_pool=16 * GB,
        fraction=DEDICATED_USABLE_FRACTION,
        gpu_vendor="amd",
        vram=16 * GB,
        graphics_class=GraphicsClass.dedicated,
        backend=ComputeBackend.rocm,
    )
    result = select_models(profile)
    assert result.quality.tag == "qwen3:14b"
    assert result.quality.quant == "Q5_K_M"  # >9B, so the upgrade quant is Q5
    assert result.quality.est_tok_s >= 10  # the 27B misses the quality floor
    assert result.fast.tag == "qwen3:8b"
    assert result.fast.quant == "Q4_K_M"
    assert result.fast.est_tok_s >= 20
    assert not result.converged


def test_tiny_machine_collapses_to_single_small_model_and_stays_local():
    """Stage 7: 4 GB of RAM, CPU-only. One small model, honest message that
    mentions the cloud option without handing off to it."""
    profile = make_profile(usable_pool=4 * GB, fraction=CPU_USABLE_FRACTION, ram=4 * GB)
    result = select_models(profile)
    assert result.weak_machine
    assert result.converged
    assert result.quality.tag == result.fast.tag
    assert result.quality.download_bytes < 2 * GB  # genuinely small
    assert any("offline" in m for m in result.messages)


def test_hopeless_machine_reports_instead_of_crashing():
    profile = make_profile(usable_pool=1 * GB, fraction=CPU_USABLE_FRACTION, ram=1 * GB)
    result = select_models(profile)
    assert result.quality is None and result.fast is None
    assert result.weak_machine
    assert result.messages
    assert result.total_download_bytes == 0
