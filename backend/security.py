"""Local-origin enforcement for the localhost API.

The app binds to 127.0.0.1, but "localhost-only" is not a security boundary by
itself — two browser-borne attacks still reach it:

- **DNS rebinding**: a malicious page whose domain re-resolves to 127.0.0.1
  becomes same-origin with the API and can read/write it freely. Blocked by
  requiring a local ``Host`` header.
- **Cross-site form POSTs**: multipart/form-encoded POSTs (e.g. the upload
  endpoint) are CORS "simple requests" that skip preflight, so any website can
  fire them blindly at localhost. Blocked by requiring that ``Origin``, when a
  browser sends one, is itself a local origin (``null`` — sandboxed iframes,
  ``file://`` pages — is rejected too).

Requests without an ``Origin`` header (same-origin GETs, curl, the packaged
launcher's health probe) pass untouched. ``NOTERATION_EXTRA_HOSTS`` (comma-
separated hostnames) extends the allowlist — the test suite uses it for
``testserver``; it is read per-request so tests never race module import.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

_LOCAL_HOSTNAMES = frozenset({"127.0.0.1", "localhost", "::1"})


def _allowed_hostnames() -> frozenset[str]:
    extra = os.environ.get("NOTERATION_EXTRA_HOSTS", "")
    if not extra:
        return _LOCAL_HOSTNAMES
    return _LOCAL_HOSTNAMES | {
        h.strip().lower() for h in extra.split(",") if h.strip()
    }


def _hostname(netloc: str) -> str | None:
    """Extract the lowercased hostname from a ``host[:port]`` value."""
    try:
        return urlsplit(f"//{netloc}").hostname
    except ValueError:
        return None


def _origin_hostname(origin: str) -> str | None:
    """Extract the lowercased hostname from an ``Origin`` header value."""
    try:
        return urlsplit(origin).hostname
    except ValueError:
        return None


def install_local_origin_guard(app: FastAPI) -> None:
    """Register the middleware that rejects non-local Host/Origin requests."""

    @app.middleware("http")
    async def enforce_local_origin(request: Request, call_next):
        allowed = _allowed_hostnames()

        host = _hostname(request.headers.get("host", ""))
        if host not in allowed:
            return JSONResponse(
                {"detail": "Invalid host header"}, status_code=400
            )

        origin = request.headers.get("origin")
        if origin is not None and _origin_hostname(origin) not in allowed:
            return JSONResponse(
                {"detail": "Cross-origin requests are not allowed"},
                status_code=403,
            )

        response = await call_next(request)
        # Belt-and-braces for served files (attachments, page renders): never
        # let a browser sniff a stored file into an executable content type.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response
