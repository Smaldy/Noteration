"""Ollama install + model-pull plumbing (Stages 5-6 execution side).

Elevation policy (per the design decision): the **only** privileged step is
installing Ollama itself, prompted at the moment the user confirms setup —
pkexec/Polkit on Linux, the UAC prompt the installer raises on Windows, and
Homebrew (or manual) on macOS. Everything else here (presence checks, starting
the server, pulling and running models) runs as the normal user. When
automatic install isn't possible (no pkexec, no brew, prompt dismissed), the
failure carries ``manual_commands()`` so the UI can show the user exactly what
to type in a terminal instead.

Network is assumed at setup time only: installing Ollama, resolving quant
tags against the registry, and pulling models all happen here, online, once.

Every OS/network call is an injectable callable on ``SetupDeps`` so the setup
orchestration (setup.py) is unit-testable without Ollama, a network, or root.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from backend.services.providers.ollama import DEFAULT_HOST

# Quant → Ollama tag suffix. The bare library tag IS the Q4_K_M build, so Q4
# needs no suffix; higher quants are separate tags that may not exist for
# every model — resolution falls back to the Q4 default (never below, spec).
QUANT_TAG_SUFFIX = {"Q5_K_M": "q5_K_M", "Q6_K": "q6_K"}

OLLAMA_INSTALL_TIMEOUT = 600  # multi-hundred-MB download on slow lines
SERVER_START_TIMEOUT = 30.0

WINDOWS_INSTALLER_URL = "https://ollama.com/download/OllamaSetup.exe"
LINUX_INSTALL_CMD = "curl -fsSL https://ollama.com/install.sh | sh"


class OllamaInstallError(Exception):
    """Automatic install failed or is impossible; the UI falls back to showing
    ``manual_commands()``."""


def manual_commands(os_name: str | None = None) -> list[str]:
    """Terminal command(s) a user can run themselves to install Ollama."""
    os_name = (os_name or platform.system()).lower()
    if os_name == "windows":
        return ["winget install Ollama.Ollama"]
    if os_name == "darwin":
        return [
            "brew install ollama",
            "# or download the app from https://ollama.com/download",
        ]
    return [LINUX_INSTALL_CMD]


def binary_present() -> bool:
    return shutil.which("ollama") is not None


def server_reachable(host: str = DEFAULT_HOST, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{host}/api/version", timeout=timeout):
            return True
    except Exception:  # noqa: BLE001 - any failure means "not reachable"
        return False


def ensure_server(host: str = DEFAULT_HOST) -> None:
    """Make the Ollama server answer, spawning ``ollama serve`` if needed.

    Runs unprivileged. On systemd installs the service is usually already up;
    this covers portable/binary installs and the just-installed case.
    """
    if server_reachable(host):
        return
    if not binary_present():
        raise OllamaInstallError("Ollama is not installed")
    subprocess.Popen(  # noqa: S603 - fixed argv, detached daemon-style
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.monotonic() + SERVER_START_TIMEOUT
    while time.monotonic() < deadline:
        if server_reachable(host):
            return
        time.sleep(0.5)
    raise OllamaInstallError("Ollama installed but its server did not start")


def install_ollama() -> None:
    """Install Ollama with a tightly-scoped elevation prompt (see module doc)."""
    os_name = platform.system().lower()
    if os_name == "linux":
        _install_linux()
    elif os_name == "darwin":
        _install_darwin()
    elif os_name == "windows":
        _install_windows()
    else:
        raise OllamaInstallError(f"Unsupported platform: {os_name}")
    if not binary_present():
        raise OllamaInstallError("Installer finished but the ollama binary was not found")


def _install_linux() -> None:
    if shutil.which("pkexec") is None:
        raise OllamaInstallError(
            "Automatic install needs pkexec (Polkit) for the one privileged step"
        )
    # The single privileged step: the official installer, via a Polkit prompt.
    result = subprocess.run(  # noqa: S603
        ["pkexec", "sh", "-c", LINUX_INSTALL_CMD],
        capture_output=True,
        text=True,
        timeout=OLLAMA_INSTALL_TIMEOUT,
    )
    if result.returncode == 126 or result.returncode == 127:
        raise OllamaInstallError("The authorization prompt was dismissed")
    if result.returncode != 0:
        raise OllamaInstallError(
            f"Installer failed: {(result.stderr or '').strip()[:300]}"
        )


def _install_darwin() -> None:
    if shutil.which("brew") is None:
        raise OllamaInstallError(
            "Automatic install on macOS needs Homebrew; install manually instead"
        )
    result = subprocess.run(  # noqa: S603
        ["brew", "install", "ollama"],
        capture_output=True,
        text=True,
        timeout=OLLAMA_INSTALL_TIMEOUT,
    )
    if result.returncode != 0:
        raise OllamaInstallError(
            f"brew install ollama failed: {(result.stderr or '').strip()[:300]}"
        )


def _install_windows() -> None:
    # The official installer is per-user and silent with /S; Windows raises its
    # own UAC prompt if elevation is required, which is exactly the scoped
    # prompt-at-install-click behavior we want.
    dest = Path(tempfile.gettempdir()) / "OllamaSetup.exe"
    try:
        urllib.request.urlretrieve(WINDOWS_INSTALLER_URL, dest)  # noqa: S310 - fixed https URL
    except Exception as exc:  # noqa: BLE001
        raise OllamaInstallError(f"Could not download the Ollama installer: {exc}")
    result = subprocess.run(  # noqa: S603
        [str(dest), "/S"], timeout=OLLAMA_INSTALL_TIMEOUT
    )
    if result.returncode != 0:
        raise OllamaInstallError(f"Installer exited with code {result.returncode}")


# -- pull-tag resolution -------------------------------------------------------


def registry_tag_exists(tag: str, timeout: float = 10.0) -> bool:
    """Whether ``library/<name>:<version>`` exists on the Ollama registry.

    Network errors read as "no" — the caller then falls back to the base tag,
    which is the safe direction (Q4_K_M default instead of a failed pull).
    """
    name, _, version = tag.partition(":")
    url = f"https://registry.ollama.ai/v2/library/{name}/manifests/{version or 'latest'}"
    request = urllib.request.Request(
        url, headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status == 200
    except Exception:  # noqa: BLE001
        return False


def resolve_pull_tag(
    base_tag: str, quant: str, tag_exists: Callable[[str], bool] = registry_tag_exists
) -> tuple[str, str | None]:
    """The pull tag for (model, quant), plus a note when it had to fall back.

    The library's bare tag is already the Q4_K_M build. A higher quant is a
    separate tag not published for every model; when absent we pull the Q4
    default rather than fail (the floor quant, never below — spec).
    """
    suffix = QUANT_TAG_SUFFIX.get(quant)
    if suffix is None:
        return base_tag, None
    candidate = f"{base_tag}-{suffix}"
    if tag_exists(candidate):
        return candidate, None
    return base_tag, (
        f"The {quant} build of {base_tag} is not published, "
        "installing the standard Q4_K_M build instead."
    )


# -- model pull ----------------------------------------------------------------


def pull_model(
    tag: str,
    on_progress: Callable[[int, int], None],
    *,
    host: str = DEFAULT_HOST,
) -> None:
    """Pull ``tag`` through the local Ollama server, streaming byte progress.

    ``on_progress(completed, total)`` fires per progress chunk (a pull walks
    several layers; the largest carries the weights, so its numbers dominate).
    Raises on any pull error — the caller owns state/retry.
    """
    import ollama  # lazy, mirrors providers/ollama.py

    client = ollama.Client(host=host)
    for chunk in client.pull(tag, stream=True):
        completed = _field(chunk, "completed") or 0
        total = _field(chunk, "total") or 0
        if total:
            on_progress(int(completed), int(total))


def installed_models(host: str = DEFAULT_HOST, timeout: float = 5.0) -> list[str]:
    """Tags currently present in the local Ollama (empty when unreachable)."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as response:
            payload = json.load(response)
        return [m.get("name", "") for m in payload.get("models", [])]
    except Exception:  # noqa: BLE001
        return []


def _field(chunk: object, key: str) -> object:
    try:
        return chunk[key]  # type: ignore[index]
    except (KeyError, TypeError, IndexError):
        return getattr(chunk, key, None)


@dataclass
class SetupDeps:
    """Everything the setup orchestration touches outside the DB, injectable."""

    binary_present: Callable[[], bool] = binary_present
    install_ollama: Callable[[], None] = install_ollama
    ensure_server: Callable[[], None] = ensure_server
    tag_exists: Callable[[str], bool] = registry_tag_exists
    pull: Callable[..., None] = pull_model
    manual_commands: Callable[[], list[str]] = field(default=manual_commands)
