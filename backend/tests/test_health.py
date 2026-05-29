"""Phase 1 smoke test: the health endpoint responds and the app boots."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unknown_api_route_404s() -> None:
    # Must 404 as an API regardless of whether the SPA bundle is mounted —
    # the catch-all must never swallow /api/* into the HTML shell.
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert "text/html" not in response.headers.get("content-type", "")
