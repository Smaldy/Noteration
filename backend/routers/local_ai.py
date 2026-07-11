"""Local AI setup endpoints — thin HTTP layer over services/local_ai/setup.py.

The long work (Ollama install, model pulls) never runs in a request handler:
``POST /install`` only flips the state row to ``queued`` and the background
install worker does the rest; the frontend polls ``GET /status`` for the
streamed progress (the same pattern the generation queue view uses).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.schemas.local_ai import InstallRequest, LocalAiStatusOut, OllamaState
from backend.services.local_ai import install as install_svc
from backend.services.local_ai import setup as setup_svc

router = APIRouter(prefix="/local-ai", tags=["local-ai"])


def _status_payload(session: Session) -> LocalAiStatusOut:
    setup = setup_svc.get_setup(session)
    reachable = install_svc.server_reachable()
    return LocalAiStatusOut.from_row(
        setup,
        ollama=OllamaState(
            binary_present=install_svc.binary_present(),
            server_reachable=reachable,
            installed_models=install_svc.installed_models() if reachable else [],
        ),
        manual_commands=install_svc.manual_commands(),
    )


@router.get("/status", response_model=LocalAiStatusOut)
def status(session: Session = Depends(get_session)) -> LocalAiStatusOut:
    return _status_payload(session)


@router.post("/detect", response_model=LocalAiStatusOut)
def detect(session: Session = Depends(get_session)) -> LocalAiStatusOut:
    try:
        setup_svc.run_detection(session)
    except setup_svc.SetupInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _status_payload(session)


@router.post("/install", response_model=LocalAiStatusOut)
def install(
    body: InstallRequest, session: Session = Depends(get_session)
) -> LocalAiStatusOut:
    try:
        setup_svc.request_install(
            session,
            quality=body.quality.model_dump() if body.quality else None,
            fast=body.fast.model_dump() if body.fast else None,
        )
    except setup_svc.SetupInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except setup_svc.NothingToInstall as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _status_payload(session)


@router.post("/reset", response_model=LocalAiStatusOut)
def reset(session: Session = Depends(get_session)) -> LocalAiStatusOut:
    try:
        setup_svc.reset_setup(session)
    except setup_svc.SetupInProgress as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _status_payload(session)
