"""Schemas for the local AI setup API (detect → confirm → install → status)."""

from __future__ import annotations

from pydantic import BaseModel

from backend.models.local_ai import LocalAiSetup


class RolePick(BaseModel):
    """One model role as confirmed by the user (possibly an override)."""

    tag: str
    quant: str = "Q4_K_M"


class InstallRequest(BaseModel):
    """Stage 5 confirmation body. Roles left out default to the detected
    selection; passing them overrides it (the low-confidence escape hatch)."""

    quality: RolePick | None = None
    fast: RolePick | None = None


class OllamaState(BaseModel):
    binary_present: bool
    server_reachable: bool
    installed_models: list[str]


class LocalAiStatusOut(BaseModel):
    """The status-aware Settings control's single source of truth."""

    status: str
    hardware: dict | None
    selection: dict | None
    chosen: dict | None
    quality_model: str | None
    fast_model: str | None
    pull_tag: str | None
    pull_completed: int
    pull_total: int
    error: str | None
    ollama: OllamaState
    manual_commands: list[str]

    @classmethod
    def from_row(
        cls,
        setup: LocalAiSetup,
        *,
        ollama: OllamaState,
        manual_commands: list[str],
    ) -> LocalAiStatusOut:
        return cls(
            status=setup.status.value,
            hardware=setup.hardware,
            selection=setup.selection,
            chosen=setup.chosen,
            quality_model=setup.quality_model,
            fast_model=setup.fast_model,
            pull_tag=setup.pull_tag,
            pull_completed=setup.pull_completed,
            pull_total=setup.pull_total,
            error=setup.error,
            ollama=ollama,
            manual_commands=manual_commands,
        )
