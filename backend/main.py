"""Noteration FastAPI app.

Serves the REST API under ``/api`` and, when present, the built React bundle
(repo-root ``dist/``) for everything else. The bundle is absent in dev/test —
the API is fully usable without it.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routers import (
    arcade,
    assessment,
    attachments,
    bookmarks,
    chapters,
    documents,
    duplicator,
    notes,
    queue,
    search,
    settings,
    study,
    subjects,
    topics,
)
from backend.migrate import run_migrations
from backend.security import install_local_origin_guard
from backend.services.pipeline.ingestion import purge_legacy_chapter_cache
from backend.services.transcription_worker import TranscriptionWorker
from backend.services.worker import QueueWorker

# Built Vite bundle. Produced by `npm run build`; gitignored.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "dist"

# Background workers that run for the app's lifetime: one drains the generation
# queue, the other transcribes uploaded audio. Both are disabled in tests (which
# drive their logic directly) via NOTERATION_DISABLE_WORKER=1.
worker = QueueWorker()
transcription_worker = TranscriptionWorker()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Start/stop the background workers alongside the app (unless disabled)."""
    started = False
    if os.environ.get("NOTERATION_DISABLE_WORKER") != "1":
        # Schema first: bare `uvicorn backend.main:app` skips the desktop
        # launcher, so this is the only upgrade path in dev.
        run_migrations()
        # One-time reclaim of chapter caches keyed by the old index format
        # (guarded here so tests never touch the real cache directory).
        purge_legacy_chapter_cache()
        worker.start()
        transcription_worker.start()
        started = True
    try:
        yield
    finally:
        if started:
            worker.stop()
            transcription_worker.stop()


app = FastAPI(title="Noteration", version="0.1.2", lifespan=lifespan)

# Reject DNS-rebinding hosts and cross-site browser requests (see security.py).
install_local_origin_guard(app)

api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by tests and the frontend boot check."""
    return {"status": "ok"}


api.include_router(subjects.router)
api.include_router(documents.router)
api.include_router(chapters.router)
api.include_router(topics.router)
api.include_router(notes.router)
api.include_router(queue.router)
api.include_router(study.router)
api.include_router(settings.router)
api.include_router(search.router)
api.include_router(bookmarks.router)
api.include_router(assessment.router)
api.include_router(attachments.router)
api.include_router(duplicator.router)
api.include_router(arcade.router)

# API routes are registered before the SPA catch-all so they always win.
app.include_router(api)


def mount_frontend() -> None:
    """Serve the built React bundle with SPA fallback, if it has been built."""
    index = FRONTEND_DIST / "index.html"
    if not index.is_file():
        return

    assets = FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        # Unknown API routes must 404 as an API, not silently return the SPA
        # shell with a 200 — otherwise fetch() gets HTML and JSON.parse fails.
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(index)


mount_frontend()
