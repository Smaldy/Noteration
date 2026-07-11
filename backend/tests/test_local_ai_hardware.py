"""Stage 1 hardware detection — profile derivation over injected probes.

Every test builds a ``Probes`` with fakes (no OS calls), which is exactly how
detection stays testable on hardware we don't own: these fixtures double as
the representative-machine set the selection stages will be scored against.
"""

from backend.services.local_ai.hardware import (
    CPU_USABLE_FRACTION,
    DEDICATED_USABLE_FRACTION,
    UNIFIED_USABLE_FRACTION,
    ComputeBackend,
    Confidence,
    GpuProbe,
    GraphicsClass,
    Probes,
    ProbeStatus,
    detect,
)

GB = 1024**3


def make_probes(
    *,
    system="Linux",
    machine="x86_64",
    ram=16 * GB,
    ram_source="psutil",
    nvidia=None,
    amd=None,
    drm_vendors=None,
    windows_gpus=None,
    apple_chip=None,
) -> Probes:
    nvidia = nvidia or GpuProbe(ProbeStatus.not_present, vendor="nvidia", source="nvml")
    amd = amd or GpuProbe(ProbeStatus.not_present, vendor="amd", source="sysfs")
    return Probes(
        system=lambda: system,
        machine=lambda: machine,
        total_ram=lambda: (ram, ram_source),
        nvidia=lambda: nvidia,
        amd=lambda: amd,
        drm_vendors=lambda: drm_vendors,
        windows_gpus=lambda: windows_gpus,
        apple_chip=lambda: apple_chip,
    )


def test_nvidia_dedicated_high_confidence():
    """The dev baseline: RTX 3060 Mobile, 6 GB VRAM read via NVML."""
    probes = make_probes(
        nvidia=GpuProbe(
            ProbeStatus.present,
            vendor="nvidia",
            name="NVIDIA GeForce RTX 3060 Laptop GPU",
            vram_bytes=6 * GB,
            source="nvml",
        ),
        drm_vendors={"10de", "1002"},  # dGPU + the Ryzen iGPU
    )
    profile = detect(probes)
    assert profile.graphics_class is GraphicsClass.dedicated
    assert profile.backend is ComputeBackend.cuda
    assert profile.vram_bytes == 6 * GB
    assert profile.usable_memory_bytes == int(6 * GB * DEDICATED_USABLE_FRACTION)
    assert profile.confidence is Confidence.high
    assert profile.sources["gpu"] == "nvml"


def test_amd_dedicated_via_sysfs():
    probes = make_probes(
        amd=GpuProbe(
            ProbeStatus.present, vendor="amd", vram_bytes=16 * GB, source="sysfs"
        ),
        drm_vendors={"1002"},
    )
    profile = detect(probes)
    assert profile.graphics_class is GraphicsClass.dedicated
    assert profile.backend is ComputeBackend.rocm
    assert profile.usable_memory_bytes == int(16 * GB * DEDICATED_USABLE_FRACTION)
    assert profile.confidence is Confidence.high


def test_biggest_gpu_wins_when_both_present():
    probes = make_probes(
        nvidia=GpuProbe(
            ProbeStatus.present, vendor="nvidia", vram_bytes=8 * GB, source="nvml"
        ),
        amd=GpuProbe(
            ProbeStatus.present, vendor="amd", vram_bytes=16 * GB, source="sysfs"
        ),
    )
    profile = detect(probes)
    assert profile.gpu_vendor == "amd"
    assert profile.vram_bytes == 16 * GB


def test_amd_apu_carveout_is_integrated_and_sized_from_ram():
    """A 512 MB carve-out is not the pool — the shared system RAM is."""
    probes = make_probes(
        ram=32 * GB,
        amd=GpuProbe(
            ProbeStatus.present, vendor="amd", vram_bytes=512 * 1024**2, source="sysfs"
        ),
    )
    profile = detect(probes)
    assert profile.graphics_class is GraphicsClass.integrated
    assert profile.usable_memory_bytes == int(32 * GB * UNIFIED_USABLE_FRACTION)
    assert profile.confidence is Confidence.medium


def test_apple_silicon_unified_memory():
    probes = make_probes(
        system="Darwin", machine="arm64", ram=32 * GB, apple_chip="Apple M2 Pro"
    )
    profile = detect(probes)
    assert profile.gpu_vendor == "apple"
    assert profile.gpu_name == "Apple M2 Pro"
    assert profile.graphics_class is GraphicsClass.integrated
    assert profile.backend is ComputeBackend.metal
    assert profile.vram_bytes is None  # unified — no separate pool
    assert profile.usable_memory_bytes == int(32 * GB * UNIFIED_USABLE_FRACTION)
    assert profile.confidence is Confidence.high


def test_apple_silicon_unknown_chip_is_medium_confidence():
    probes = make_probes(system="Darwin", machine="arm64", ram=16 * GB)
    profile = detect(probes)
    assert profile.confidence is Confidence.medium
    assert profile.backend is ComputeBackend.metal


def test_windows_registry_dedicated():
    probes = make_probes(
        system="Windows",
        machine="AMD64",
        windows_gpus=[
            GpuProbe(
                ProbeStatus.present,
                vendor="intel",
                name="Intel(R) UHD Graphics",
                vram_bytes=128 * 1024**2,
                source="registry",
            ),
            GpuProbe(
                ProbeStatus.present,
                vendor="nvidia",
                name="NVIDIA GeForce RTX 4070",
                vram_bytes=12 * GB,
                source="registry",
            ),
        ],
    )
    profile = detect(probes)
    assert profile.arch == "x86_64"
    assert profile.gpu_vendor == "nvidia"  # dGPU preferred over the iGPU entry
    assert profile.graphics_class is GraphicsClass.dedicated
    assert profile.usable_memory_bytes == int(12 * GB * DEDICATED_USABLE_FRACTION)
    assert profile.confidence is Confidence.high


def test_cpu_only_definitive_is_high_confidence():
    """Both vendor probes answered not_present — RAM sizing is trustworthy."""
    probes = make_probes(ram=16 * GB, drm_vendors=set())
    profile = detect(probes)
    assert profile.graphics_class is GraphicsClass.cpu_only
    assert profile.backend is ComputeBackend.cpu
    assert profile.usable_memory_bytes == int(16 * GB * CPU_USABLE_FRACTION)
    assert profile.confidence is Confidence.high


def test_intel_igpu_only_is_cpu_class():
    probes = make_probes(ram=8 * GB, drm_vendors={"8086"})
    profile = detect(probes)
    assert profile.graphics_class is GraphicsClass.cpu_only
    assert profile.confidence is Confidence.high


def test_absence_is_not_zero_unsized_gpu_goes_low_confidence():
    """DRM says an NVIDIA device exists, but NVML and nvidia-smi are absent.

    The profile must NOT claim cpu-only-with-high-confidence: it sizes
    conservatively from RAM, drops to low confidence, and says why — this is
    what makes Stage 5's override UX prominent.
    """
    probes = make_probes(
        ram=16 * GB,
        nvidia=GpuProbe(
            ProbeStatus.unknown,
            vendor="nvidia",
            source="nvml",
            detail="NVML shared library not found",
        ),
        drm_vendors={"10de"},
    )
    profile = detect(probes)
    assert profile.confidence is Confidence.low
    assert profile.usable_memory_bytes == int(16 * GB * CPU_USABLE_FRACTION)
    assert any("could not be read" in note for note in profile.notes)


def test_nothing_readable_at_all_is_low_confidence():
    probes = make_probes(
        ram=16 * GB,
        nvidia=GpuProbe(ProbeStatus.unknown, vendor="nvidia", source="nvml"),
        amd=GpuProbe(ProbeStatus.unknown, vendor="amd", source="sysfs"),
        drm_vendors=None,  # no /sys/class/drm either (e.g. a container)
    )
    profile = detect(probes)
    assert profile.confidence is Confidence.low
    assert profile.graphics_class is GraphicsClass.cpu_only


def test_never_raises_with_no_ram_reading():
    probes = make_probes(ram=None, ram_source="unavailable", drm_vendors=set())
    profile = detect(probes)
    assert profile.usable_memory_bytes == int(8 * GB * CPU_USABLE_FRACTION)
    assert profile.confidence is Confidence.low
    assert profile.notes
