"""Exercise Duplicator Stage 1 — extraction service + API (Wave ED-2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models.duplicator import ExerciseSession, ExtractedExercise
from backend.models.enums import ExerciseSessionStatus
from backend.services.duplicator import sessions as sessionsvc
from backend.services.duplicator.extraction import extract_exercises
from backend.services.pipeline.ingestion import IngestionResult
from backend.services.providers.base import ProviderResult

_MINIMAL_PDF = b"%PDF-1.4\n%fake bytes for tests\n"


class _FakeVisionWaterfall:
    """Returns a queued response per ``transcribe_image`` call (one per page)."""

    def __init__(self, page_texts: list[str]) -> None:
        self._texts = list(page_texts)
        self.prompts: list[str | None] = []
        self.calls = 0

    def transcribe_image(
        self, image: bytes, *, max_tokens: int = 1024, prompt: str | None = None
    ) -> ProviderResult:
        self.prompts.append(prompt)
        text = self._texts[self.calls] if self.calls < len(self._texts) else "[]"
        self.calls += 1
        return ProviderResult(text=text, provider="mock_vision")


def _arr(*items: dict) -> str:
    return json.dumps(list(items))


def _ex(raw_text: str, topic: str = "calculus.limits", **extra) -> dict:
    return {"raw_text": raw_text, "topic": topic, **extra}


def _new_session(db: Session, **kw) -> ExerciseSession:
    es = ExerciseSession(document_hash="h", year_level=kw.pop("year_level", 3), **kw)
    db.add(es)
    db.flush()
    return es


# --- extract_exercises (in-memory `session` fixture) ------------------------


def test_extract_persists_rows_with_fields(session: Session) -> None:
    es = _new_session(session, subject_hint="complex analysis")
    viz = {"type": "mafs_function", "expression": "x^2", "domain": [-3, 3]}
    wf = _FakeVisionWaterfall(
        [
            _arr(
                _ex(
                    "Compute lim x->0 sin(x)/x.",
                    topic="calculus.limits",
                    subtopic="trig",
                    difficulty_signals=["standard"],
                ),
                _ex("Graph f(x)=x^2.", topic="calculus.functions", viz=viz),
            )
        ]
    )

    rows = extract_exercises(session, es, wf, load_pages=lambda h: [b"png"])

    assert len(rows) == 2
    assert es.status is ExerciseSessionStatus.ready
    first, second = rows
    assert first.order_index == 0 and second.order_index == 1
    assert first.subtopic == "trig"
    assert first.difficulty_signals == ["standard"]
    assert second.viz == viz
    # The extraction prompt (not the default LaTeX one) reached the vision call.
    assert "JSON array" in (wf.prompts[0] or "")


def test_extract_tolerates_malformed(session: Session) -> None:
    es = _new_session(session)
    page1 = 'Here are the problems: [{"raw_text": "Valid one", "topic": "t"}, 42, '
    page1 += '{"topic": "missing text"}]'  # one valid, one int, one no raw_text
    page2 = "Sorry, I could not read this page."  # no JSON array at all
    wf = _FakeVisionWaterfall([page1, page2])

    rows = extract_exercises(session, es, wf, load_pages=lambda h: [b"a", b"b"])

    assert [r.raw_text for r in rows] == ["Valid one"]
    assert es.status is ExerciseSessionStatus.ready


def test_extract_dedup_across_pages(session: Session) -> None:
    es = _new_session(session)
    page1 = _arr(_ex("Prove the intermediate value theorem.", topic="analysis.ivt"),
                 _ex("Find the derivative of x^3.", topic="calculus.derivatives"))
    # Page 2 repeats the second problem (continuation) plus a new one.
    page2 = _arr(_ex("Find the derivative of x^3.", topic="calculus.derivatives"),
                 _ex("State Rolle's theorem.", topic="analysis.rolle"))
    wf = _FakeVisionWaterfall([page1, page2])

    rows = extract_exercises(session, es, wf, load_pages=lambda h: [b"a", b"b"])

    texts = [r.raw_text for r in rows]
    assert texts == [
        "Prove the intermediate value theorem.",
        "Find the derivative of x^3.",
        "State Rolle's theorem.",
    ]
    assert [r.order_index for r in rows] == [0, 1, 2]


def test_create_session_roundtrip(session: Session, tmp_path: Path) -> None:
    wf = _FakeVisionWaterfall([_arr(_ex("Solve 2x+1=5.", topic="algebra.linear"))])

    def _fake_ingest(pdf_path: Path) -> IngestionResult:
        return IngestionResult(
            file_hash="cafebabe",
            markdown="",
            markdown_path=None,
            page_image_paths=[],
            page_count=1,
            is_scanned=False,
            from_cache=False,
        )

    created = sessionsvc.create_session(
        session,
        data=_MINIMAL_PDF,
        filename="ex.pdf",
        year_level=2,
        subject_hint="  ",  # blank → normalised to None
        waterfall=wf,
        ingest_fn=_fake_ingest,
        uploads_dir=tmp_path / "uploads",
        load_pages=lambda h: [b"png"],
    )

    assert created.document_hash == "cafebabe"
    assert created.subject_hint is None
    assert created.status is ExerciseSessionStatus.ready

    fetched = sessionsvc.get_exercise_session(session, created.id)
    assert [e.raw_text for e in fetched.exercises] == ["Solve 2x+1=5."]
    assert fetched.exercises[0].results == []


def test_create_session_rejects_non_pdf(session: Session, tmp_path: Path) -> None:
    from backend.services.documents import InvalidPDFError

    with pytest.raises(InvalidPDFError):
        sessionsvc.create_session(
            session,
            data=b"not a pdf",
            filename="x.pdf",
            year_level=1,
            subject_hint=None,
            waterfall=_FakeVisionWaterfall([]),
            uploads_dir=tmp_path,
        )
    # Nothing persisted.
    assert session.scalars(select(ExerciseSession)).all() == []


# --- HTTP (StaticPool shared in-memory DB across the TestClient thread) ------


def test_post_bad_year_level_422(client: TestClient) -> None:
    resp = client.post(
        "/api/duplicator/sessions",
        files={"file": ("e.pdf", _MINIMAL_PDF, "application/pdf")},
        data={"year_level": "7"},
    )
    assert resp.status_code == 422


def test_post_non_pdf_422(client: TestClient) -> None:
    resp = client.post(
        "/api/duplicator/sessions",
        files={"file": ("e.pdf", b"not a pdf", "application/pdf")},
        data={"year_level": "3"},
    )
    assert resp.status_code == 422


def test_get_unknown_session_404(client: TestClient) -> None:
    assert client.get("/api/duplicator/sessions/999").status_code == 404


def test_get_returns_session_with_exercises(client: TestClient, db_factory) -> None:
    with db_factory() as db:
        es = ExerciseSession(document_hash="h", year_level=4)
        es.exercises.append(
            ExtractedExercise(order_index=0, raw_text="Q1", topic="algebra.groups")
        )
        db.add(es)
        db.commit()
        sid = es.id

    resp = client.get(f"/api/duplicator/sessions/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["year_level"] == 4
    assert body["exercises"][0]["raw_text"] == "Q1"
    assert body["exercises"][0]["results"] == []
