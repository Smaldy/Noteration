"""Stage 1 hardware detection for the local AI setup flow.

Produces a ``HardwareProfile`` with the spec's two independent outputs:
**usable memory** (driven by dedicated / integrated / CPU-only) and the
**compute backend** (driven by architecture/vendor, which gates what is
eligible to run). The two are deliberately never blended into one number.

Every vendor probe is tri-state (``present`` / ``not_present`` / ``unknown``)
so a missing tool never reads as "no GPU" — absence is not zero. A device
enumeration that needs no vendor driver (``/sys/class/drm`` vendor ids on
Linux, the display-class registry on Windows) supplies the ground truth of
what hardware exists; the vendor probes size it. When enumeration says a GPU
exists but no probe could size it, the profile says so and drops to low
confidence instead of silently claiming CPU-only.

All OS calls are injectable callables on ``Probes`` (the same pattern as the
providers' injectable client/clock), so the detectors and the downstream
selection logic are unit-testable on hardware we don't own.
"""

from __future__ import annotations

import enum
import glob
import os
import platform
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field

# Usable-memory fractions (spec Stage 1). Dedicated VRAM is a model-only pool;
# integrated/unified memory is shared with the OS; CPU-only leaves generous
# headroom so the machine stays usable while a model is loaded.
DEDICATED_USABLE_FRACTION = 0.875
UNIFIED_USABLE_FRACTION = 0.675
CPU_USABLE_FRACTION = 0.60

# An AMD/Intel device reporting less dedicated VRAM than this is a shared-memory
# carve-out (an APU/iGPU aperture), not a real dedicated pool.
INTEGRATED_VRAM_THRESHOLD = 2 * 1024**3

# PCI vendor ids as they appear in sysfs / PNP device ids.
PCI_VENDOR_NAMES = {"10de": "nvidia", "1002": "amd", "8086": "intel"}

# GGUF K-quants run on every backend Ollama ships (CUDA, ROCm, Metal, CPU —
# including ARM). The field exists so a future format restriction has a home;
# today it never varies.
GGUF_QUANTS = ("Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0")


class ProbeStatus(enum.StrEnum):
    present = "present"
    not_present = "not_present"  # probed successfully; hardware genuinely absent
    unknown = "unknown"  # tool missing or probe errored — NOT "no hardware"


class GraphicsClass(enum.StrEnum):
    dedicated = "dedicated"
    integrated = "integrated"  # includes Apple unified memory
    cpu_only = "cpu_only"


class ComputeBackend(enum.StrEnum):
    cuda = "cuda"
    rocm = "rocm"
    metal = "metal"
    cpu = "cpu"


class Confidence(enum.StrEnum):
    """How much Stage 5's confirm screen should trust (vs. question) this profile."""

    high = "high"  # memory pool read directly from the device/OS
    medium = "medium"  # derived by a principled rule (e.g. shared-memory fraction)
    low = "low"  # guessed, or hardware exists that no probe could size


@dataclass(frozen=True)
class GpuProbe:
    """One vendor probe's raw result. ``vram_bytes`` only means anything when
    ``status`` is ``present``; ``detail`` says why a probe came back unknown."""

    status: ProbeStatus
    vendor: str | None = None
    name: str | None = None
    vram_bytes: int | None = None
    source: str = ""
    detail: str | None = None


@dataclass(frozen=True)
class HardwareProfile:
    """Stage 1 output — everything selection (Stages 2-4/7) and the Stage 5
    confirm screen need. ``sources`` records how each fact was obtained (it
    rides into the copy-detection-report blob); ``notes`` are honest caveats
    for the user."""

    os_name: str  # "linux" / "windows" / "darwin"
    arch: str  # "x86_64" / "arm64" / raw machine string
    ram_bytes: int | None
    gpu_vendor: str | None
    gpu_name: str | None
    vram_bytes: int | None
    graphics_class: GraphicsClass
    backend: ComputeBackend
    usable_memory_bytes: int
    eligible_quants: tuple[str, ...]
    confidence: Confidence
    sources: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


# -- real probes (each lazily imports / degrades to `unknown`, never raises) --


def _real_total_ram() -> tuple[int | None, str]:
    """Total system RAM in bytes plus the source that provided it."""
    try:
        import psutil  # lazy — tests inject fakes and never need it

        return int(psutil.virtual_memory().total), "psutil"
    except Exception:  # noqa: BLE001 - degrade to the stdlib path
        pass
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"), "sysconf"
    except (ValueError, OSError, AttributeError):
        return None, "unavailable"


def _probe_nvidia_nvml() -> GpuProbe:
    try:
        import pynvml  # lazy; ships as nvidia-ml-py
    except Exception:  # noqa: BLE001
        return GpuProbe(
            ProbeStatus.unknown,
            vendor="nvidia",
            source="nvml",
            detail="nvidia-ml-py not installed",
        )
    try:
        pynvml.nvmlInit()
    except Exception as exc:  # noqa: BLE001 - NVMLError: driver/library absent
        # Cannot tell "no NVIDIA GPU" from "NVIDIA GPU without a driver" here;
        # the DRM/registry enumeration cross-checks this in the orchestrator.
        return GpuProbe(
            ProbeStatus.unknown, vendor="nvidia", source="nvml", detail=str(exc)
        )
    try:
        count = pynvml.nvmlDeviceGetCount()
        if count == 0:
            return GpuProbe(ProbeStatus.not_present, vendor="nvidia", source="nvml")
        best_name, best_vram = None, -1
        for i in range(count):
            handle = pynvml.nvmlDeviceGetHandleByIndex(i)
            total = int(pynvml.nvmlDeviceGetMemoryInfo(handle).total)
            if total > best_vram:
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode(errors="replace")
                best_name, best_vram = name, total
        return GpuProbe(
            ProbeStatus.present,
            vendor="nvidia",
            name=best_name,
            vram_bytes=best_vram,
            source="nvml",
        )
    except Exception as exc:  # noqa: BLE001
        return GpuProbe(
            ProbeStatus.unknown, vendor="nvidia", source="nvml", detail=str(exc)
        )
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:  # noqa: BLE001
            pass


def _probe_nvidia_smi() -> GpuProbe:
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return GpuProbe(
            ProbeStatus.unknown,
            vendor="nvidia",
            source="nvidia-smi",
            detail="nvidia-smi not on PATH",
        )
    except Exception as exc:  # noqa: BLE001
        return GpuProbe(
            ProbeStatus.unknown, vendor="nvidia", source="nvidia-smi", detail=str(exc)
        )
    if out.returncode != 0:
        return GpuProbe(
            ProbeStatus.unknown,
            vendor="nvidia",
            source="nvidia-smi",
            detail=(out.stderr or "").strip()[:200] or f"exit {out.returncode}",
        )
    best_name, best_vram = None, -1
    for line in out.stdout.strip().splitlines():
        name, _, mib = line.rpartition(",")
        try:
            vram = int(mib.strip()) * 1024**2
        except ValueError:
            continue
        if vram > best_vram:
            best_name, best_vram = name.strip(), vram
    if best_vram < 0:
        return GpuProbe(ProbeStatus.not_present, vendor="nvidia", source="nvidia-smi")
    return GpuProbe(
        ProbeStatus.present,
        vendor="nvidia",
        name=best_name,
        vram_bytes=best_vram,
        source="nvidia-smi",
    )


def _probe_nvidia() -> GpuProbe:
    """NVML in-process first; ``nvidia-smi`` as the subprocess fallback."""
    probe = _probe_nvidia_nvml()
    if probe.status is not ProbeStatus.unknown:
        return probe
    fallback = _probe_nvidia_smi()
    return fallback if fallback.status is not ProbeStatus.unknown else probe


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read().strip()
    except OSError:
        return None


def _probe_amd_sysfs() -> GpuProbe:
    """AMD VRAM via sysfs — world-readable, needs no ROCm install at all."""
    cards = glob.glob("/sys/class/drm/card[0-9]*/device")
    if not cards:
        return GpuProbe(
            ProbeStatus.unknown,
            vendor="amd",
            source="sysfs",
            detail="/sys/class/drm has no cards (not Linux, or no DRM)",
        )
    best_vram, seen_amd = -1, False
    for card in cards:
        vendor = (_read_text(os.path.join(card, "vendor")) or "").removeprefix("0x")
        if vendor != "1002":
            continue
        seen_amd = True
        raw = _read_text(os.path.join(card, "mem_info_vram_total"))
        try:
            best_vram = max(best_vram, int(raw)) if raw is not None else best_vram
        except ValueError:
            continue
    if not seen_amd:
        return GpuProbe(ProbeStatus.not_present, vendor="amd", source="sysfs")
    if best_vram < 0:
        detail = "AMD device present but mem_info_vram_total unreadable"
        return GpuProbe(
            ProbeStatus.unknown, vendor="amd", source="sysfs", detail=detail
        )
    return GpuProbe(
        ProbeStatus.present, vendor="amd", vram_bytes=best_vram, source="sysfs"
    )


def _real_drm_vendors() -> set[str] | None:
    """PCI vendor ids of display devices (Linux ground truth), None off-Linux."""
    cards = glob.glob("/sys/class/drm/card[0-9]*/device/vendor")
    if not cards:
        return None
    vendors: set[str] = set()
    for path in cards:
        raw = _read_text(path)
        if raw:
            vendors.add(raw.removeprefix("0x").lower())
    return vendors


# Display-adapter device class in the Windows registry. Every video device has a
# numbered subkey here with DriverDesc + HardwareInformation.qwMemorySize (a
# QWORD — unlike WMI's uint32 AdapterRAM, it does not cap at 4 GB).
_WIN_DISPLAY_CLASS = (
    r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
)


def _probe_windows_registry() -> list[GpuProbe] | None:
    """All display adapters from the registry; None when not on Windows."""
    try:
        import winreg  # lazy — only exists on Windows
    except ImportError:
        return None
    probes: list[GpuProbe] = []
    try:
        root = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _WIN_DISPLAY_CLASS)
    except OSError:
        return probes
    with root:
        index = 0
        while True:
            try:
                sub = winreg.EnumKey(root, index)
            except OSError:
                break
            index += 1
            if not re.fullmatch(r"\d{4}", sub):
                continue
            try:
                with winreg.OpenKey(root, sub) as key:
                    probes.append(_windows_adapter_probe(winreg, key))
            except OSError:
                continue
    return probes


def _windows_adapter_probe(winreg, key) -> GpuProbe:  # noqa: ANN001 - winreg types are Windows-only
    def read(name: str):
        try:
            return winreg.QueryValueEx(key, name)[0]
        except OSError:
            return None

    name = read("DriverDesc")
    device_id = str(read("MatchingDeviceId") or "").lower()
    vendor = None
    match = re.search(r"ven_([0-9a-f]{4})", device_id)
    if match:
        vendor = PCI_VENDOR_NAMES.get(match.group(1))
    vram = read("HardwareInformation.qwMemorySize")
    if vram is None:
        # Legacy DWORD fallback; caps at 4 GB so only trust it for small values.
        vram = read("HardwareInformation.MemorySize")
        if isinstance(vram, bytes):
            vram = int.from_bytes(vram[:8], "little")
    if not isinstance(vram, int) or vram <= 0:
        return GpuProbe(
            ProbeStatus.unknown,
            vendor=vendor,
            name=name,
            source="registry",
            detail="adapter present but no readable memory size",
        )
    return GpuProbe(
        ProbeStatus.present,
        vendor=vendor,
        name=name,
        vram_bytes=vram,
        source="registry",
    )


def _real_apple_chip() -> str | None:
    """The chip name macOS reports, e.g. "Apple M2 Pro"."""
    try:
        out = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:  # noqa: BLE001
        return None
    return out.stdout.strip() or None


@dataclass
class Probes:
    """Every OS/vendor call the detector makes, injectable for tests."""

    system: Callable[[], str] = platform.system
    machine: Callable[[], str] = platform.machine
    total_ram: Callable[[], tuple[int | None, str]] = _real_total_ram
    nvidia: Callable[[], GpuProbe] = _probe_nvidia
    amd: Callable[[], GpuProbe] = _probe_amd_sysfs
    drm_vendors: Callable[[], set[str] | None] = _real_drm_vendors
    windows_gpus: Callable[[], list[GpuProbe] | None] = _probe_windows_registry
    apple_chip: Callable[[], str | None] = _real_apple_chip


def _normalize_arch(machine: str) -> str:
    m = machine.lower()
    if m in ("x86_64", "amd64"):
        return "x86_64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return machine


def _usable(pool_bytes: int, fraction: float) -> int:
    return int(pool_bytes * fraction)


def detect(probes: Probes | None = None) -> HardwareProfile:
    """Run Stage 1 detection and derive the profile.

    Never raises: every probe degrades to ``unknown`` and the orchestrator
    resolves unknowns into confidence + notes instead of exceptions, so the
    setup flow always has *a* profile to show at the confirm step.
    """
    probes = probes or Probes()
    os_name = probes.system().lower()
    arch = _normalize_arch(probes.machine())
    ram_bytes, ram_source = probes.total_ram()
    sources = {"ram": ram_source, "arch": "platform"}
    notes: list[str] = []

    if os_name == "darwin" and arch == "arm64":
        return _profile_apple(probes, ram_bytes, sources, notes)
    gpu = _best_windows_gpu(probes) if os_name == "windows" else _best_unix_gpu(probes)

    if gpu.status is ProbeStatus.present:
        return _profile_with_gpu(os_name, arch, ram_bytes, gpu, sources, notes)
    if gpu.status is ProbeStatus.unknown:
        # Hardware exists (or might) that nothing could size. Stay functional:
        # size against system RAM like CPU-only, but say so and go low-confidence
        # so Stage 5 pushes the user to check/override.
        vendor = f" ({gpu.vendor})" if gpu.vendor else ""
        notes.append(
            f"A display device{vendor} was found but its memory could not be "
            f"read ({gpu.detail or 'no probe succeeded'}). Sizing conservatively "
            "from system RAM; please check the values below."
        )
        sources["gpu"] = gpu.source or "none"
        return _profile_cpu(
            os_name, arch, ram_bytes, sources, notes, confidence=Confidence.low
        )
    sources["gpu"] = gpu.source or "enumeration"
    return _profile_cpu(
        os_name,
        arch,
        ram_bytes,
        sources,
        notes,
        confidence=Confidence.high if ram_bytes else Confidence.low,
    )


# -- per-branch profile builders ----------------------------------------------


def _profile_apple(
    probes: Probes,
    ram_bytes: int | None,
    sources: dict[str, str],
    notes: list[str],
) -> HardwareProfile:
    chip = probes.apple_chip()
    sources["gpu"] = "sysctl"
    if ram_bytes is None:
        notes.append("Could not read system RAM; assuming a minimal 8 GB pool.")
        ram_bytes = 8 * 1024**3
        confidence = Confidence.low
    else:
        # Unified memory IS the system RAM pool, read directly; the fraction is
        # the documented sharing model, not a guess.
        confidence = Confidence.high
    return HardwareProfile(
        os_name="darwin",
        arch="arm64",
        ram_bytes=ram_bytes,
        gpu_vendor="apple",
        gpu_name=chip,
        vram_bytes=None,  # unified — there is no separate VRAM pool
        graphics_class=GraphicsClass.integrated,
        backend=ComputeBackend.metal,
        usable_memory_bytes=_usable(ram_bytes, UNIFIED_USABLE_FRACTION),
        eligible_quants=GGUF_QUANTS,
        confidence=confidence if chip else Confidence.medium,
        sources=sources,
        notes=notes,
    )


def _best_windows_gpu(probes: Probes) -> GpuProbe:
    adapters = probes.windows_gpus()
    if adapters is None:
        return GpuProbe(
            ProbeStatus.unknown, source="registry", detail="registry unavailable"
        )
    sized = [a for a in adapters if a.status is ProbeStatus.present]
    if sized:
        # Prefer real dedicated pools over iGPU carve-outs, then the biggest.
        return max(
            sized,
            key=lambda a: (a.vendor not in (None, "intel"), a.vram_bytes or 0),
        )
    unsized = [a for a in adapters if a.status is ProbeStatus.unknown]
    if unsized:
        return unsized[0]
    return GpuProbe(ProbeStatus.not_present, source="registry")


def _best_unix_gpu(probes: Probes) -> GpuProbe:
    nvidia = probes.nvidia()
    amd = probes.amd()
    present = [
        p
        for p in (nvidia, amd)
        if p.status is ProbeStatus.present and p.vram_bytes is not None
    ]
    if present:
        return max(present, key=lambda p: p.vram_bytes or 0)

    # Nothing sized. Use the driver-independent DRM enumeration to decide
    # between "genuinely no GPU" and "GPU present but unreadable".
    vendors = probes.drm_vendors() or set()
    names = {PCI_VENDOR_NAMES.get(v) for v in vendors} - {None, "intel"}
    for probe in (nvidia, amd):
        if probe.status is ProbeStatus.unknown and probe.vendor in names:
            return probe  # enumeration confirms this unsized vendor exists
    if "intel" in {PCI_VENDOR_NAMES.get(v) for v in vendors}:
        # Intel iGPU only — shared memory, CPU-class throughput for LLMs.
        return GpuProbe(
            ProbeStatus.not_present, vendor="intel", source="drm-enumeration"
        )
    if nvidia.status is ProbeStatus.unknown and amd.status is ProbeStatus.unknown:
        # No enumeration and no probe worked (e.g. exotic container) — unknown.
        return GpuProbe(
            ProbeStatus.unknown,
            source="none",
            detail=f"nvidia: {nvidia.detail}; amd: {amd.detail}",
        )
    return GpuProbe(ProbeStatus.not_present, source="drm-enumeration")


def _profile_with_gpu(
    os_name: str,
    arch: str,
    ram_bytes: int | None,
    gpu: GpuProbe,
    sources: dict[str, str],
    notes: list[str],
) -> HardwareProfile:
    sources["gpu"] = gpu.source
    vram = gpu.vram_bytes or 0
    integrated = gpu.vendor == "intel" or (
        gpu.vendor == "amd" and vram < INTEGRATED_VRAM_THRESHOLD
    )
    backend = {
        "nvidia": ComputeBackend.cuda,
        "amd": ComputeBackend.rocm,
    }.get(gpu.vendor or "", ComputeBackend.cpu)
    if integrated:
        # A carve-out is not the usable pool — the shared system RAM is.
        pool = ram_bytes or vram
        if ram_bytes is None:
            notes.append("Could not read system RAM; sizing from the VRAM carve-out.")
        return HardwareProfile(
            os_name=os_name,
            arch=arch,
            ram_bytes=ram_bytes,
            gpu_vendor=gpu.vendor,
            gpu_name=gpu.name,
            vram_bytes=gpu.vram_bytes,
            graphics_class=GraphicsClass.integrated,
            backend=backend if gpu.vendor == "amd" else ComputeBackend.cpu,
            usable_memory_bytes=_usable(pool, UNIFIED_USABLE_FRACTION),
            eligible_quants=GGUF_QUANTS,
            confidence=Confidence.medium if ram_bytes else Confidence.low,
            sources=sources,
            notes=notes,
        )
    return HardwareProfile(
        os_name=os_name,
        arch=arch,
        ram_bytes=ram_bytes,
        gpu_vendor=gpu.vendor,
        gpu_name=gpu.name,
        vram_bytes=gpu.vram_bytes,
        graphics_class=GraphicsClass.dedicated,
        backend=backend,
        usable_memory_bytes=_usable(vram, DEDICATED_USABLE_FRACTION),
        eligible_quants=GGUF_QUANTS,
        confidence=Confidence.high,
        sources=sources,
        notes=notes,
    )


def _profile_cpu(
    os_name: str,
    arch: str,
    ram_bytes: int | None,
    sources: dict[str, str],
    notes: list[str],
    *,
    confidence: Confidence,
) -> HardwareProfile:
    if ram_bytes is None:
        notes.append("Could not read system RAM; assuming a minimal 8 GB pool.")
        pool = 8 * 1024**3
    else:
        pool = ram_bytes
    return HardwareProfile(
        os_name=os_name,
        arch=arch,
        ram_bytes=ram_bytes,
        gpu_vendor=None,
        gpu_name=None,
        vram_bytes=None,
        graphics_class=GraphicsClass.cpu_only,
        backend=ComputeBackend.cpu,
        usable_memory_bytes=_usable(pool, CPU_USABLE_FRACTION),
        eligible_quants=GGUF_QUANTS,
        confidence=confidence,
        sources=sources,
        notes=notes,
    )
