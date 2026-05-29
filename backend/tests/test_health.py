"""Phase 1 smoke test: the health endpoint responds and the app boots."""

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
