"""Background install worker — drives the local AI setup to completion.

A small sibling of ``TranscriptionWorker``: one daemon thread that polls the
``LocalAiSetup`` row and runs ``process_setup_once`` when it is queued or was
interrupted mid-install (Ollama pulls resume from partial layers, so a
restart just picks up where it left off). One tick can take minutes — the
model pulls are multi-GB — which is fine: this thread owns nothing else.
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy.orm import Session, sessionmaker

from backend.db.database import SessionLocal
from backend.services.local_ai.setup import process_setup_once

logger = logging.getLogger("backend.local_ai")

POLL_INTERVAL_SECONDS = 2.0


class LocalAiInstallWorker:
    """Owns the background thread that installs Ollama + pulls the models."""

    def __init__(
        self,
        session_factory: sessionmaker[Session] = SessionLocal,
        *,
        poll_interval: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._session_factory = session_factory
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="noteration-local-ai-worker", daemon=True
        )
        self._thread.start()
        logger.info("Local AI install worker started (poll=%ss)", self._poll_interval)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("Local AI install worker stopped")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # noqa: BLE001 - a bad tick must not kill the thread
                logger.exception("Local AI install worker tick failed; continuing")
            self._stop.wait(self._poll_interval)

    def _tick(self) -> None:
        session = self._session_factory()
        try:
            process_setup_once(session)
        finally:
            session.close()
