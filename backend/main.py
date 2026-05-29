"""Noteration FastAPI app.

Serves the REST API under ``/api`` and, when present, the built React bundle
(repo-root ``dist/``) for everything else. The bundle is absent in dev/test —
the API is fully usable without it.
"""

from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Built Vite bundle. Produced by `npm run build`; gitignored.
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "dist"

app = FastAPI(title="Noteration", version="0.1.0")

api = APIRouter(prefix="/api")


@api.get("/health")
def health() -> dict[str, str]:
    """Liveness probe used by tests and the frontend boot check."""
    return {"status": "ok"}


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
