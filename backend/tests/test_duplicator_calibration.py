"""Exercise Duplicator calibration export/import + samples (Wave ED-4)."""

from __future__ import annotations

import io
import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401
from backend.db.database import Base, get_session
from backend.main import app
from backend.models.duplicator import CalibrationSample, ExerciseSession
from backend.models.enums import CalibrationSource
from backend.services.duplicator import calibration as cal
from backend.services.duplicator import sessions as sessionsvc
from backend.services.pipeline.ingestion import IngestionResult
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall


def _add(session: Session, **kw) -> CalibrationSample:
    kw.setdefault("topic", "algebra.groups")
    kw.setdefault("subtopic", None)
    kw.setdefault("year_level", 3)
    kw.setdefault("source_text", "Prove Lagrange's theorem.")
    return cal.add_sample(session, **kw)


# --- service ----------------------------------------------------------------


def test_add_sample_defaults_own(session: Session) -> None:
    sample = _add(session)
    assert sample.id is not None
    assert sample.source is CalibrationSource.own


def test_export_round_trips_shape(session: Session) -> None:
    _add(session, topic="t1", source_text="a", subtopic="s")
    _add(session, topic="t2", source_text="b", year_level=5)
    data = cal.export_calibration(session)
    assert data["schema_version"] == cal.SCHEMA_VERSION
    assert len(data["samples"]) == 2
    first = data["samples"][0]
    assert set(first) == {"topic", "subtopic", "year_level", "source_text", "source"}
    assert first["source"] == "own"


def test_import_dedupes_and_tags_source(session: Session) -> None:
    payload = {
        "schema_version": 1,
        "samples": [
            {"topic": "t", "subtopic": None, "year_level": 2, "source_text": "x"},
            {"topic": "t", "subtopic": "s", "year_level": 2, "source_text": "y"},
        ],
    }
    imported, skipped = cal.import_calibration(session, payload)
    assert (imported, skipped) == (2, 0)
    # Re-import the same data → all skipped (exact-duplicate match).
    imported2, skipped2 = cal.import_calibration(session, payload)
    assert (imported2, skipped2) == (0, 2)
    # Imported rows are tagged.
    rows = session.scalars(select(CalibrationSample)).all()
    assert {r.source for r in rows} == {CalibrationSource.imported}


def test_import_skips_malformed(session: Session) -> None:
    payload = {
        "samples": [
            {"topic": "ok", "year_level": 1, "source_text": "good"},
            {"topic": "", "year_level": 1, "source_text": "blank topic"},
            {"topic": "no_text", "year_level": 1},
            {"topic": "bad_year", "year_level": "x", "source_text": "t"},
            "not a dict",
        ]
    }
    imported, skipped = cal.import_calibration(session, payload)
    assert imported == 1
    assert skipped == 4


def test_import_handles_garbage_top_level(session: Session) -> None:
    assert cal.import_calibration(session, {"nope": 1}) == (0, 0)
    assert cal.import_calibration(session, {"samples": "notalist"}) == (0, 0)


def test_create_session_records_own_samples(session: Session, tmp_path) -> None:
    wf = Waterfall(
        [
            MockProvider(
                "vis",
                supports_vision=True,
                text=json.dumps(
                    [{"raw_text": "Prove X.", "topic": "analysis.proof"}]
                ),
            )
        ]
    )

    def _fake_ingest(_p):
        return IngestionResult(
            file_hash="h",
            markdown="",
            markdown_path=None,
            page_image_paths=[],
            page_count=1,
            is_scanned=False,
            from_cache=False,
        )

    sessionsvc.create_session(
        session,
        data=b"%PDF-1.4\nx",
        filename="ex.pdf",
        year_level=4,
        subject_hint=None,
        waterfall=wf,
        ingest_fn=_fake_ingest,
        uploads_dir=tmp_path,
        load_pages=lambda h: [b"png"],
    )
    samples = session.scalars(select(CalibrationSample)).all()
    assert len(samples) == 1
    assert samples[0].source is CalibrationSource.own
    assert samples[0].topic == "analysis.proof"
    assert samples[0].year_level == 4


# --- HTTP -------------------------------------------------------------------


@pytest.fixture
def db_factory() -> Generator[sessionmaker, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record) -> None:  # noqa: ANN001
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def client(db_factory: sessionmaker) -> Generator[TestClient, None, None]:
    def _override() -> Generator[Session, None, None]:
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_http_export_has_attachment_header(client: TestClient, db_factory) -> None:
    with db_factory() as db:
        _add(db, topic="http.t", source_text="z")
    resp = client.get("/api/duplicator/calibration/export")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert "noteration-calibration.json" in resp.headers["content-disposition"]
    assert resp.json()["samples"][0]["topic"] == "http.t"


def test_http_import_roundtrip(client: TestClient) -> None:
    payload = {"samples": [{"topic": "t", "year_level": 1, "source_text": "x"}]}
    file = io.BytesIO(json.dumps(payload).encode())
    resp = client.post(
        "/api/duplicator/calibration/import",
        files={"file": ("cal.json", file, "application/json")},
    )
    assert resp.status_code == 200
    assert resp.json() == {"imported": 1, "skipped": 0}


def test_http_import_bad_json_422(client: TestClient) -> None:
    file = io.BytesIO(b"not json at all")
    resp = client.post(
        "/api/duplicator/calibration/import",
        files={"file": ("cal.json", file, "application/json")},
    )
    assert resp.status_code == 422


def test_http_add_sample_201(client: TestClient) -> None:
    resp = client.post(
        "/api/duplicator/calibration/samples",
        json={"topic": "calc.limits", "year_level": 2, "source_text": "Find lim."},
    )
    assert resp.status_code == 201
    assert "id" in resp.json()


def test_http_add_sample_bad_year_422(client: TestClient) -> None:
    resp = client.post(
        "/api/duplicator/calibration/samples",
        json={"topic": "t", "year_level": 9, "source_text": "x"},
    )
    assert resp.status_code == 422
