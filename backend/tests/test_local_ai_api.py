"""Local AI setup API — the detect/confirm/status surface the Settings UI uses.

Real hardware detection and Ollama presence checks are monkeypatched: API
tests must not depend on the machine running the suite.
"""

import pytest

from backend.services.local_ai import setup as setup_svc
from backend.services.local_ai.hardware import (
    ComputeBackend,
    Confidence,
    GraphicsClass,
    HardwareProfile,
)

GB = 1024**3


@pytest.fixture(autouse=True)
def fake_environment(monkeypatch):
    """Pin detection to a fixed profile and Ollama probes to 'absent'."""
    profile = HardwareProfile(
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
    monkeypatch.setattr(setup_svc, "detect", lambda: profile)
    from backend.routers import local_ai as router_module

    monkeypatch.setattr(router_module.install_svc, "binary_present", lambda: False)
    monkeypatch.setattr(
        router_module.install_svc, "server_reachable", lambda *a, **k: False
    )


def test_status_starts_not_configured(client):
    payload = client.get("/api/local-ai/status").json()
    assert payload["status"] == "not_configured"
    assert payload["ollama"] == {
        "binary_present": False,
        "server_reachable": False,
        "installed_models": [],
    }
    assert payload["manual_commands"]  # the type-it-yourself path is always shown


def test_detect_returns_profile_selection_and_confidence(client):
    payload = client.post("/api/local-ai/detect").json()
    assert payload["status"] == "detected"
    assert payload["hardware"]["confidence"] == "high"
    assert payload["selection"]["quality"]["tag"] == "qwen3:14b"
    assert payload["selection"]["fast"]["tag"] == "qwen3:4b"
    assert payload["selection"]["converged"] is False


def test_install_requires_detection_first(client):
    response = client.post("/api/local-ai/install", json={})
    assert response.status_code == 400


def test_install_queues_with_selection_defaults(client):
    client.post("/api/local-ai/detect")
    payload = client.post("/api/local-ai/install", json={}).json()
    assert payload["status"] == "queued"
    assert payload["chosen"]["quality"]["tag"] == "qwen3:14b"
    assert payload["chosen"]["fast"]["tag"] == "qwen3:4b"


def test_install_accepts_user_override(client):
    """Stage 5's low-confidence escape hatch: the user picks other models."""
    client.post("/api/local-ai/detect")
    payload = client.post(
        "/api/local-ai/install",
        json={
            "quality": {"tag": "qwen3:8b", "quant": "Q4_K_M"},
            "fast": {"tag": "llama3.2:3b", "quant": "Q4_K_M"},
        },
    ).json()
    assert payload["chosen"]["quality"]["tag"] == "qwen3:8b"
    assert payload["chosen"]["fast"]["tag"] == "llama3.2:3b"


def test_detect_conflicts_while_install_runs(client):
    client.post("/api/local-ai/detect")
    client.post("/api/local-ai/install", json={})
    assert client.post("/api/local-ai/detect").status_code == 409
    assert client.post("/api/local-ai/reset").status_code == 409


def test_reset_returns_to_not_configured(client):
    client.post("/api/local-ai/detect")
    payload = client.post("/api/local-ai/reset").json()
    assert payload["status"] == "not_configured"
    assert payload["selection"] is None


def test_settings_expose_two_model_fields(client):
    payload = client.get("/api/settings").json()
    assert payload["ollama_fast_model"] is None
    assert payload["ollama_always_model"] is None
    assert payload["ollama_prefer_quality"] is False
    updated = client.patch(
        "/api/settings", json={"ollama_prefer_quality": True}
    ).json()
    assert updated["ollama_prefer_quality"] is True


def test_settings_manual_role_pins_set_and_clear(client):
    updated = client.patch(
        "/api/settings",
        json={
            "ollama_fast_model": "qwen3:8b",
            "ollama_quality_model": "gemma3:27b",
            "ollama_always_model": "phi4",
        },
    ).json()
    assert updated["ollama_fast_model"] == "qwen3:8b"
    assert updated["ollama_always_model"] == "phi4"
    # Empty string clears a role (mirrors the API-key clearing convention).
    cleared = client.patch("/api/settings", json={"ollama_always_model": ""}).json()
    assert cleared["ollama_always_model"] is None
    assert cleared["ollama_fast_model"] == "qwen3:8b"
