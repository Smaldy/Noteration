"""Local AI setup orchestration — state machine, install worker tick, routing.

Everything outside the DB is injected through ``SetupDeps`` fakes: no Ollama,
no network, no elevation. The API surface is covered in
``test_local_ai_api.py``; this file drives the service layer directly.
"""

import pytest

from backend.models.enums import LocalAiStatus, QueueLaneState
from backend.models.hierarchy import Subject
from backend.models.settings import Settings
from backend.services.local_ai.hardware import (
    ComputeBackend,
    Confidence,
    GraphicsClass,
    HardwareProfile,
)
from backend.services.local_ai.install import OllamaInstallError, SetupDeps
from backend.services.local_ai.runtime import resolve_ollama_model
from backend.services.local_ai.setup import (
    NothingToInstall,
    SetupInProgress,
    get_setup,
    process_setup_once,
    request_install,
    reset_setup,
    run_detection,
)
from backend.services.providers.ollama import OllamaProvider
from backend.services.settings import get_settings
from backend.services.worker import _provider_for_job

GB = 1024**3


def profile_3060() -> HardwareProfile:
    return HardwareProfile(
        os_name="linux",
        arch="x86_64",
        ram_bytes=16 * GB,
        gpu_vendor="nvidia",
        gpu_name="NVIDIA GeForce RTX 3060 Laptop GPU",
        vram_bytes=6 * GB,
        graphics_class=GraphicsClass.dedicated,
        backend=ComputeBackend.cuda,
        usable_memory_bytes=int(6 * GB * 0.875),
        eligible_quants=("Q4_K_M", "Q5_K_M", "Q6_K"),
        confidence=Confidence.high,
    )


class FakeDeps(SetupDeps):
    """Recording fakes for every side effect the setup flow performs."""

    def __init__(
        self,
        *,
        binary=True,
        install_fails: str | None = None,
        existing_tags: set[str] | None = None,
        pull_fails: str | None = None,
    ) -> None:
        self.installed_ollama = False
        self.pulled: list[str] = []
        tags = existing_tags if existing_tags is not None else {"any"}

        def install() -> None:
            if install_fails:
                raise OllamaInstallError(install_fails)
            self.installed_ollama = True

        def pull(tag, on_progress, **_kwargs) -> None:
            if pull_fails:
                raise RuntimeError(pull_fails)
            on_progress(1 * GB, 3 * GB)
            on_progress(3 * GB, 3 * GB)
            self.pulled.append(tag)

        super().__init__(
            binary_present=lambda: binary,
            install_ollama=install,
            ensure_server=lambda: None,
            tag_exists=lambda tag: ("any" in tags) or tag in tags,
            pull=pull,
            manual_commands=lambda: ["curl -fsSL https://ollama.com/install.sh | sh"],
        )


def detected(session) -> None:
    run_detection(session, profile=profile_3060())


def test_detection_snapshots_profile_and_selection(session):
    setup = run_detection(session, profile=profile_3060())
    assert setup.status is LocalAiStatus.detected
    assert setup.hardware["gpu_name"] == "NVIDIA GeForce RTX 3060 Laptop GPU"
    # The 3060 golden selection (test_local_ai_selection) rides in the snapshot.
    assert setup.selection["quality"]["tag"] == "qwen3:14b"
    assert setup.selection["fast"]["tag"] == "qwen3:4b"
    assert setup.selection["converged"] is False


def test_install_requires_a_selection(session):
    with pytest.raises(NothingToInstall):
        request_install(session)


def test_confirmation_gate_nothing_pulls_before_install(session):
    """Stage 5: detection alone must never download anything."""
    detected(session)
    setup = get_setup(session)
    assert setup.status is LocalAiStatus.detected
    deps = FakeDeps()
    assert process_setup_once(session, deps=deps) is False
    assert deps.pulled == []


def test_happy_path_pulls_both_roles_and_configures_settings(session):
    detected(session)
    request_install(session)
    deps = FakeDeps(binary=False)
    assert process_setup_once(session, deps=deps) is True
    setup = get_setup(session)
    assert deps.installed_ollama  # auto-install ran (no prompt gate on Ollama)
    assert deps.pulled == ["qwen3:14b-q5_K_M", "qwen3:4b-q6_K"]  # quality, fast
    assert setup.status is LocalAiStatus.ready
    assert setup.quality_model == "qwen3:14b-q5_K_M"
    assert setup.fast_model == "qwen3:4b-q6_K"
    assert setup.pull_completed == setup.pull_total == 3 * GB
    settings = get_settings(session)
    assert settings.ollama_enabled is True
    assert settings.ollama_fast_model == "qwen3:4b-q6_K"
    assert settings.ollama_quality_model == "qwen3:14b-q5_K_M"


def test_converged_choice_pulls_once(session):
    """When both roles are the same (model, quant), the tag downloads once."""
    detected(session)
    request_install(
        session,
        quality={"tag": "qwen3:4b", "quant": "Q6_K"},
        fast={"tag": "qwen3:4b", "quant": "Q6_K"},
    )
    deps = FakeDeps()
    process_setup_once(session, deps=deps)
    setup = get_setup(session)
    assert setup.status is LocalAiStatus.ready
    assert deps.pulled == ["qwen3:4b-q6_K"]
    assert setup.quality_model == setup.fast_model == "qwen3:4b-q6_K"


def test_missing_quant_tag_falls_back_to_q4_default(session):
    detected(session)
    request_install(session)
    deps = FakeDeps(existing_tags=set())  # no quant variants published
    process_setup_once(session, deps=deps)
    setup = get_setup(session)
    assert setup.status is LocalAiStatus.ready
    assert deps.pulled == ["qwen3:14b", "qwen3:4b"]  # bare tags ARE the Q4 builds
    assert any("Q4_K_M" in m for m in setup.selection["messages"])


def test_ollama_install_failure_reports_manual_commands(session):
    detected(session)
    request_install(session)
    deps = FakeDeps(binary=False, install_fails="The authorization prompt was dismissed")
    process_setup_once(session, deps=deps)
    setup = get_setup(session)
    assert setup.status is LocalAiStatus.failed
    assert "authorization prompt" in setup.error
    assert "install.sh" in setup.error  # the type-it-yourself fallback
    assert get_settings(session).ollama_enabled is False


def test_pull_failure_lands_in_failed_and_is_retryable(session):
    detected(session)
    request_install(session)
    process_setup_once(session, deps=FakeDeps(pull_fails="connection reset"))
    setup = get_setup(session)
    assert setup.status is LocalAiStatus.failed
    assert "connection reset" in setup.error
    # Re-confirming retries: back to queued, then a clean run succeeds.
    request_install(session)
    deps = FakeDeps()
    process_setup_once(session, deps=deps)
    assert get_setup(session).status is LocalAiStatus.ready


def test_interrupted_pull_resumes_on_next_tick(session):
    """A row left in ``pulling`` by a crash is picked up again (Ollama resumes
    partial layers, so re-pulling is safe and cheap)."""
    detected(session)
    request_install(session)
    setup = get_setup(session)
    setup.status = LocalAiStatus.pulling  # simulate the crash-time state
    session.commit()
    deps = FakeDeps()
    assert process_setup_once(session, deps=deps) is True
    assert get_setup(session).status is LocalAiStatus.ready


def test_detect_and_install_conflict_while_running(session):
    detected(session)
    request_install(session)
    with pytest.raises(SetupInProgress):
        run_detection(session, profile=profile_3060())
    with pytest.raises(SetupInProgress):
        request_install(session)


def test_reset_clears_setup_and_detaches_settings(session):
    detected(session)
    request_install(session)
    process_setup_once(session, deps=FakeDeps())
    reset_setup(session)
    setup = get_setup(session)
    assert setup.status is LocalAiStatus.not_configured
    assert setup.selection is None and setup.quality_model is None
    settings = get_settings(session)
    assert settings.ollama_enabled is False
    assert settings.ollama_fast_model is None


# -- runtime model routing ---------------------------------------------------


def make_settings(**kwargs) -> Settings:
    settings = Settings(id=1, **kwargs)
    return settings


def test_resolve_overnight_gets_quality_foreground_gets_fast():
    settings = make_settings(
        ollama_fast_model="qwen3:8b", ollama_quality_model="gemma3:27b-q5_K_M"
    )
    assert resolve_ollama_model(settings, overnight=True) == "gemma3:27b-q5_K_M"
    assert resolve_ollama_model(settings, overnight=False) == "qwen3:8b"


def test_resolve_always_pin_overrides_everything():
    settings = make_settings(
        ollama_fast_model="qwen3:8b",
        ollama_quality_model="gemma3:27b-q5_K_M",
        ollama_always_model="phi4",
        ollama_prefer_quality=True,
    )
    assert resolve_ollama_model(settings, overnight=True) == "phi4"
    assert resolve_ollama_model(settings, overnight=False) == "phi4"


def test_resolve_prefer_quality_toggle_and_fallbacks():
    settings = make_settings(
        ollama_fast_model="qwen3:8b",
        ollama_quality_model="gemma3:27b-q5_K_M",
        ollama_prefer_quality=True,
    )
    assert resolve_ollama_model(settings, overnight=False) == "gemma3:27b-q5_K_M"
    # Legacy single-model installs keep working untouched.
    legacy = make_settings(ollama_model="llama3.1")
    assert resolve_ollama_model(legacy, overnight=True) == "llama3.1"
    assert resolve_ollama_model(legacy, overnight=False) == "llama3.1"
    # One-role setups serve that role everywhere.
    single = make_settings(ollama_quality_model="qwen3:4b-q6_K")
    assert resolve_ollama_model(single, overnight=False) == "qwen3:4b-q6_K"


def test_worker_swaps_ollama_model_for_overnight_lane(session):
    """The Stage 6 hardwiring: an overnight lane's claim runs on the quality
    model even though the waterfall was built with the fast default."""
    from backend.models.enums import QueueStage
    from backend.models.hierarchy import Chapter, Document, Topic
    from backend.models.processing import QueueJob

    subject = Subject(name="S", queue_state=QueueLaneState.overnight)
    session.add(subject)
    session.flush()
    document = Document(subject_id=subject.id, filename="f.pdf", file_hash="h")
    session.add(document)
    session.flush()
    chapter = Chapter(document_id=document.id, subject_id=subject.id, title="C")
    session.add(chapter)
    session.flush()
    topic = Topic(chapter_id=chapter.id, title="T")
    session.add(topic)
    session.flush()
    job = QueueJob(topic_id=topic.id, subject_id=subject.id, stage=QueueStage.notes)
    session.add(job)
    settings = get_settings(session)
    settings.ollama_fast_model = "qwen3:8b"
    settings.ollama_quality_model = "gemma3:27b-q5_K_M"
    session.commit()

    fast_provider = OllamaProvider(model="qwen3:8b", enabled=True)
    swapped = _provider_for_job(session, fast_provider, job)
    assert swapped is not fast_provider
    assert swapped.model == "gemma3:27b-q5_K_M"

    subject.queue_state = QueueLaneState.running
    session.commit()
    assert _provider_for_job(session, fast_provider, job) is fast_provider
