"""Local AI setup orchestration — detect, confirm, install, resume.

The state machine over ``LocalAiSetup`` (models/local_ai.py):

    not_configured → detected → queued → installing_ollama → pulling → ready
                        ↑__________________________________________↓ failed

``run_detection`` and ``request_install`` are the router's synchronous calls;
``process_setup_once`` is the install worker's tick and does the long work
(install Ollama, resolve tags, pull models). A row found mid-install on boot
is simply processed again: Ollama's pull resumes partial layers, so the flow
is restart-safe without any extra bookkeeping.

The Stage 5 gate lives in the split between the calls: nothing is downloaded
until ``request_install`` — the user's explicit confirmation — flips the row
to ``queued``.
"""

from __future__ import annotations

import dataclasses
import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.enums import LocalAiStatus
from backend.models.local_ai import SETUP_ID, LocalAiSetup
from backend.services.local_ai.hardware import HardwareProfile, detect
from backend.services.local_ai.install import (
    OllamaInstallError,
    SetupDeps,
    resolve_pull_tag,
)
from backend.services.local_ai.selection import select_models
from backend.services.settings import get_settings

logger = logging.getLogger("backend.local_ai")

# Statuses the install worker owns; everything else is at rest.
IN_PROGRESS = (
    LocalAiStatus.queued,
    LocalAiStatus.installing_ollama,
    LocalAiStatus.pulling,
)
# Commit pull progress only every this-many new bytes so a fast local pull
# doesn't hammer the single-writer SQLite with per-chunk commits.
PROGRESS_COMMIT_BYTES = 32 * 1024**2


class SetupInProgress(Exception):
    """Raised when a call would disturb a queued/running install."""


class NothingToInstall(Exception):
    """Raised when install is requested without a detection/selection to act on."""


def get_setup(session: Session) -> LocalAiSetup:
    """Return the setup singleton, creating it if absent (same pattern as
    services/settings.get_settings — concurrent first-creates are benign)."""
    setup = session.get(LocalAiSetup, SETUP_ID)
    if setup is not None:
        return setup
    setup = LocalAiSetup(id=SETUP_ID)
    session.add(setup)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return session.get(LocalAiSetup, SETUP_ID)
    session.refresh(setup)
    return setup


def run_detection(
    session: Session, profile: HardwareProfile | None = None
) -> LocalAiSetup:
    """Stage 1-4: detect (or accept an injected profile), select, snapshot."""
    setup = get_setup(session)
    if setup.status in IN_PROGRESS:
        raise SetupInProgress("An install is already running")
    profile = profile or detect()
    selection = select_models(profile)
    setup.hardware = dataclasses.asdict(profile)
    setup.selection = dataclasses.asdict(selection)
    setup.status = LocalAiStatus.detected
    setup.error = None
    setup.chosen = None
    setup.pull_tag = None
    setup.pull_completed = 0
    setup.pull_total = 0
    session.commit()
    session.refresh(setup)
    return setup


def request_install(
    session: Session,
    *,
    quality: dict | None = None,
    fast: dict | None = None,
) -> LocalAiSetup:
    """Stage 5 confirmation: record what to install and queue the worker.

    ``quality``/``fast`` are ``{"tag": ..., "quant": ...}`` overrides; absent
    roles default to the stored selection. This is the explicit-confirmation
    gate — nothing downloads before this call.
    """
    setup = get_setup(session)
    if setup.status in IN_PROGRESS:
        raise SetupInProgress("An install is already running")
    selection = setup.selection or {}
    quality = quality or selection.get("quality")
    fast = fast or selection.get("fast")
    if not quality and not fast:
        raise NothingToInstall("Run detection first or pass explicit models")
    setup.chosen = {"quality": quality, "fast": fast}
    setup.status = LocalAiStatus.queued
    setup.error = None
    setup.pull_tag = None
    setup.pull_completed = 0
    setup.pull_total = 0
    session.commit()
    session.refresh(setup)
    return setup


def reset_setup(session: Session) -> LocalAiSetup:
    """Back to square one (the Settings "remove" action). Clears the setup row
    and detaches the models from Settings; pulled files stay on disk (removing
    them is Ollama's business, surfaced separately in the UI if ever)."""
    setup = get_setup(session)
    if setup.status in IN_PROGRESS:
        raise SetupInProgress("An install is already running")
    setup.status = LocalAiStatus.not_configured
    setup.hardware = None
    setup.selection = None
    setup.chosen = None
    setup.quality_model = None
    setup.fast_model = None
    setup.pull_tag = None
    setup.pull_completed = 0
    setup.pull_total = 0
    setup.error = None
    settings = get_settings(session)
    settings.ollama_fast_model = None
    settings.ollama_quality_model = None
    settings.ollama_enabled = False
    session.commit()
    session.refresh(setup)
    return setup


def process_setup_once(session: Session, *, deps: SetupDeps | None = None) -> bool:
    """One install-worker tick: advance an in-progress setup to done/failed.

    Returns False when there is nothing to do. Any failure lands in
    ``failed`` with the reason (and the manual commands, when Ollama itself
    couldn't be installed) — the user re-confirms to retry.
    """
    deps = deps or SetupDeps()
    setup = get_setup(session)
    if setup.status not in IN_PROGRESS:
        return False
    try:
        _ensure_ollama(session, setup, deps)
        _pull_chosen(session, setup, deps)
    except OllamaInstallError as exc:
        commands = " ".join(deps.manual_commands())
        _fail(session, setup, f"{exc}. To install manually, run: {commands}")
        return True
    except Exception as exc:  # noqa: BLE001 - any failure must land in `failed`, not kill the worker
        logger.exception("Local AI setup failed")
        _fail(session, setup, str(exc))
        return True

    settings = get_settings(session)
    settings.ollama_quality_model = setup.quality_model
    settings.ollama_fast_model = setup.fast_model
    settings.ollama_enabled = True
    setup.status = LocalAiStatus.ready
    setup.pull_tag = None
    session.commit()
    return True


# -- internals -------------------------------------------------------------


def _ensure_ollama(session: Session, setup: LocalAiSetup, deps: SetupDeps) -> None:
    if not deps.binary_present():
        setup.status = LocalAiStatus.installing_ollama
        session.commit()
        deps.install_ollama()  # the one privileged step (see install.py)
    deps.ensure_server()


def _pull_chosen(session: Session, setup: LocalAiSetup, deps: SetupDeps) -> None:
    chosen = setup.chosen or {}
    notes: list[str] = []
    resolved: dict[str, str] = {}
    # Resolve first (cheap registry checks), then pull each distinct tag once —
    # converged selections choose the same model twice but download it once.
    for role in ("quality", "fast"):
        pick = chosen.get(role)
        if not pick:
            continue
        tag, note = resolve_pull_tag(pick["tag"], pick.get("quant", ""), deps.tag_exists)
        resolved[role] = tag
        if note:
            notes.append(note)

    setup.status = LocalAiStatus.pulling
    session.commit()
    for tag in dict.fromkeys(resolved.values()):  # unique, order-preserving
        setup.pull_tag = tag
        setup.pull_completed = 0
        setup.pull_total = 0
        session.commit()
        last_committed = 0

        def on_progress(completed: int, total: int) -> None:
            nonlocal last_committed
            setup.pull_completed = completed
            setup.pull_total = total
            if completed - last_committed >= PROGRESS_COMMIT_BYTES or completed == total:
                last_committed = completed
                session.commit()

        deps.pull(tag, on_progress)
        session.commit()  # flush the final progress state for this tag

    setup.quality_model = resolved.get("quality")
    setup.fast_model = resolved.get("fast")
    # Fallback notes ride on the error field's sibling: keep them visible in the
    # selection snapshot so the status UI can show "installed Q4 instead".
    if notes and setup.selection is not None:
        selection = dict(setup.selection)
        selection["messages"] = list(selection.get("messages", [])) + notes
        setup.selection = selection
    session.commit()


def _fail(session: Session, setup: LocalAiSetup, message: str) -> None:
    session.rollback()
    setup = session.get(LocalAiSetup, SETUP_ID)
    setup.status = LocalAiStatus.failed
    setup.error = message
    setup.pull_tag = None
    session.commit()
