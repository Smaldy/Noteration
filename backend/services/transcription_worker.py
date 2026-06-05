"""Background transcription worker — turns uploaded audio into transcripts.

A small sibling of the queue worker (``services/worker.py``): a single daemon
thread that, every ``poll_interval``, transcribes the oldest ``transcribing``
audio document with Gemini 3.1 Flash. One at a time, its own short-lived session
per tick, never spins (skips entirely when Gemini isn't configured), and survives
a bad tick. A document stuck mid-transcription across a restart is simply picked
up again on the next poll (it's still ``transcribing``), so recovery is automatic.
"""

from __future__ import annotations

import logging
import threading

from sqlalchemy.orm import Session, sessionmaker

from backend.db.database import SessionLocal
from backend.services.settings import get_settings
from backend.services.transcription import (
    make_gemini_transcriber,
    transcribe_pending_document,
)

logger = logging.getLogger("backend.transcription_worker")

POLL_INTERVAL_SECONDS = 5.0


def transcribe_once(session: Session) -> int | None:
    """Transcribe one pending audio document if Gemini is configured (else no-op).

    Directly unit-testable one-shot of the worker's per-tick work.
    """
    settings = get_settings(session)
    # Transcription always uses Gemini's audio model — it's independent of the
    # ``gemini_enabled`` generation-tier toggle (a user testing Ollama for notes
    # still wants audio transcribed). It only needs a Gemini key.
    if not settings.api_key_gemini:
        return None  # no key yet → leave audio docs transcribing until one lands
    transcriber = make_gemini_transcriber(settings.api_key_gemini, settings.language)
    return transcribe_pending_document(session, transcriber=transcriber)


class TranscriptionWorker:
    """Owns the background thread that transcribes audio for the running app."""

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
            target=self._run, name="noteration-transcription-worker", daemon=True
        )
        self._thread.start()
        logger.info("Transcription worker started (poll=%ss)", self._poll_interval)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        logger.info("Transcription worker stopped")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception:  # noqa: BLE001 - a bad tick must not kill the thread
                logger.exception("Transcription worker tick failed; continuing")
            self._stop.wait(self._poll_interval)

    def _tick(self) -> None:
        session = self._session_factory()
        try:
            done = transcribe_once(session)
            if done is not None:
                logger.info("Transcribed document %s", done)
        finally:
            session.close()
