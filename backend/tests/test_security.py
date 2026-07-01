"""Local-origin guard tests: DNS-rebinding hosts and cross-site origins are
rejected, while local/dev/test traffic passes untouched."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app


def _client() -> TestClient:
    # raise_server_exceptions off isn't needed — the guard answers before routing.
    return TestClient(app)


def test_local_host_allowed() -> None:
    with _client() as client:
        response = client.get("/api/health", headers={"Host": "127.0.0.1:8000"})
    assert response.status_code == 200


def test_localhost_and_testserver_hosts_allowed() -> None:
    with _client() as client:
        for host in ("localhost:8000", "localhost", "testserver"):
            response = client.get("/api/health", headers={"Host": host})
            assert response.status_code == 200, host


def test_rebound_host_rejected() -> None:
    """A DNS-rebinding page reaches 127.0.0.1 with its own Host header — 400."""
    with _client() as client:
        response = client.get("/api/health", headers={"Host": "evil.example.com"})
    assert response.status_code == 400


def test_rebound_host_with_port_rejected() -> None:
    with _client() as client:
        response = client.get(
            "/api/health", headers={"Host": "evil.example.com:8000"}
        )
    assert response.status_code == 400


def test_cross_site_origin_rejected() -> None:
    """A cross-site form POST carries the attacker page's Origin — 403."""
    with _client() as client:
        response = client.post(
            "/api/documents",
            headers={"Origin": "https://evil.example.com"},
            files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
            data={"subject_id": "1"},
        )
    assert response.status_code == 403


def test_null_origin_rejected() -> None:
    """Sandboxed-iframe / file:// pages send `Origin: null` — 403."""
    with _client() as client:
        response = client.get("/api/health", headers={"Origin": "null"})
    assert response.status_code == 403


def test_local_origin_allowed() -> None:
    """The app's own origin (packaged pywebview window, dev browser) passes."""
    with _client() as client:
        response = client.get(
            "/api/health", headers={"Origin": "http://127.0.0.1:8000"}
        )
    assert response.status_code == 200


def test_nosniff_header_set() -> None:
    with _client() as client:
        response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
