"""Audio transcription tests: upload → transcribe → notes flow (Wave 3).

The model call is injected, so these exercise the persistence/status logic and the
HTTP routing without any network.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app
from backend.models import Document, Subject
from backend.models.enums import DocumentStatus, QueueLaneState, QueueStage
from backend.models.processing import QueueJob
from backend.schemas.structure import ChapterIn, TopicIn
from backend.services import documents as docsvc
from backend.services import transcription as tx
from backend.services.providers.base import (
    ProviderLimitError,
    ProviderUnavailableError,
)
from backend.services.transcription_worker import transcribe_once


def _subject(session: Session) -> Subject:
    subject = Subject(name="Physics")
    session.add(subject)
    session.commit()
    return subject


def _audio_doc(session: Session, tmp_path: Path, name: str = "lecture.mp3") -> Document:
    subject = _subject(session)
    return docsvc.create_audio_document(
        session,
        subject_id=subject.id,
        filename=name,
        data=b"fake-audio-bytes",
        uploads_dir=tmp_path,
    )


def _fake_preparer(n_chunks: int) -> tx.PreparerFn:
    """A preparer that fabricates ``n_chunks`` chunk files without ffmpeg."""

    def _prep(audio_path: Path, work_dir: Path, *, ext: str, trim: bool = True) -> list[Path]:
        work_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for i in range(n_chunks):
            chunk = work_dir / f"chunk-{i:03d}{ext}"
            chunk.write_bytes(b"audio")
            paths.append(chunk)
        return paths

    return _prep


# --- helpers ----------------------------------------------------------------


def test_is_audio_filename() -> None:
    assert tx.is_audio_filename("lecture.mp3")
    assert tx.is_audio_filename("Recording.M4A")
    assert tx.is_audio_filename("talk.wav")
    assert not tx.is_audio_filename("notes.pdf")
    assert not tx.is_audio_filename("plain.txt")


def test_audio_mime_for() -> None:
    assert tx.audio_mime_for("a.mp3") == "audio/mp3"
    assert tx.audio_mime_for("a.flac") == "audio/flac"
    assert tx.audio_mime_for("a.unknown") == "audio/mp3"  # safe default


def test_build_prompt_uses_language() -> None:
    assert "Italian" in tx.build_transcription_prompt("it")
    assert "English" in tx.build_transcription_prompt("xx")  # falls back


# --- upload + transcribe service --------------------------------------------


def test_create_audio_document_persists_and_marks_transcribing(
    session: Session, tmp_path: Path
) -> None:
    doc = _audio_doc(session, tmp_path)
    assert doc.source_type == "audio"
    assert doc.status == DocumentStatus.transcribing
    assert doc.markdown_path is None
    assert tx.audio_path_for(doc, tmp_path).is_file()  # stored as <hash>.mp3


def test_create_audio_rejects_non_audio(session: Session, tmp_path: Path) -> None:
    subject = _subject(session)
    with pytest.raises(docsvc.InvalidAudioError):
        docsvc.create_audio_document(
            session,
            subject_id=subject.id,
            filename="slides.pdf",
            data=b"%PDF",
            uploads_dir=tmp_path,
        )


def test_transcribe_pending_success(session: Session, tmp_path: Path) -> None:
    doc = _audio_doc(session, tmp_path)
    markdown = "## Kinematics\n\nVelocity is dx/dt."
    acted = tx.transcribe_pending_document(
        session,
        transcriber=lambda _p, _m: markdown,
        uploads_dir=tmp_path,
        preparer=_fake_preparer(1),
    )
    assert acted == doc.id
    session.refresh(doc)
    assert doc.status == DocumentStatus.uploaded
    assert doc.status_detail is None
    assert doc.markdown_path is not None
    assert Path(doc.markdown_path).read_text(encoding="utf-8") == markdown
    # The chunk workspace is cleaned up once the transcript is assembled.
    assert not tx.chunks_dir_for(doc, tmp_path).exists()


def test_transcribe_pending_concatenates_chunks(
    session: Session, tmp_path: Path
) -> None:
    doc = _audio_doc(session, tmp_path)
    acted = tx.transcribe_pending_document(
        session,
        transcriber=lambda p, _m: f"text {Path(p).stem}",
        uploads_dir=tmp_path,
        preparer=_fake_preparer(3),
    )
    assert acted == doc.id
    session.refresh(doc)
    assert doc.status == DocumentStatus.uploaded
    text = Path(doc.markdown_path).read_text(encoding="utf-8")
    # All three chunks, in order, joined into one transcript.
    assert text == "text chunk-000\n\ntext chunk-001\n\ntext chunk-002"


def test_transcribe_pending_rate_limited_keeps_progress(
    session: Session, tmp_path: Path
) -> None:
    doc = _audio_doc(session, tmp_path)

    def _limited(_p: str, _m: str) -> str:
        raise ProviderLimitError("429 RESOURCE_EXHAUSTED")

    acted = tx.transcribe_pending_document(
        session,
        transcriber=_limited,
        uploads_dir=tmp_path,
        preparer=_fake_preparer(2),
    )
    assert acted == doc.id
    session.refresh(doc)
    # A rate limit no longer fails the document — it stays resumable.
    assert doc.status == DocumentStatus.transcribing
    assert "resuming" in (doc.status_detail or "").lower()
    work = tx.chunks_dir_for(doc, tmp_path)
    assert (work / "progress.json").is_file()
    assert not (work / "chunk-000.md").exists()


def test_resumes_after_rate_limit(session: Session, tmp_path: Path) -> None:
    doc = _audio_doc(session, tmp_path)
    prep = _fake_preparer(3)
    base = datetime(2026, 6, 6, tzinfo=UTC)

    def _fail_on_second(path: str, _m: str) -> str:
        if "chunk-001" in path:
            raise ProviderLimitError("429")
        return f"text {Path(path).stem}"

    # Pass 1: chunk-000 succeeds, chunk-001 is rate-limited → paused mid-way.
    tx.transcribe_pending_document(
        session,
        transcriber=_fail_on_second,
        uploads_dir=tmp_path,
        preparer=prep,
        clock=lambda: base,
    )
    session.refresh(doc)
    assert doc.status == DocumentStatus.transcribing
    work = tx.chunks_dir_for(doc, tmp_path)
    assert (work / "chunk-000.md").is_file()
    assert not (work / "chunk-001.md").exists()

    # Still inside the backoff window → nothing is due yet.
    assert (
        tx.transcribe_pending_document(
            session,
            transcriber=_fail_on_second,
            uploads_dir=tmp_path,
            preparer=prep,
            clock=lambda: base,
        )
        is None
    )

    # Pass 2: after the backoff, a healthy provider finishes the rest. The
    # preparer is NOT re-run (chunks are cached); only the missing chunks transcribe.
    later = base + timedelta(minutes=10)
    acted = tx.transcribe_pending_document(
        session,
        transcriber=lambda p, _m: f"text {Path(p).stem}",
        uploads_dir=tmp_path,
        preparer=prep,
        clock=lambda: later,
    )
    assert acted == doc.id
    session.refresh(doc)
    assert doc.status == DocumentStatus.uploaded
    text = Path(doc.markdown_path).read_text(encoding="utf-8")
    assert "text chunk-000" in text
    assert "text chunk-001" in text
    assert "text chunk-002" in text


def test_transcribe_pending_unavailable_sets_error(
    session: Session, tmp_path: Path
) -> None:
    doc = _audio_doc(session, tmp_path)

    def _down(_p: str, _m: str) -> str:
        raise ProviderUnavailableError("network down")

    tx.transcribe_pending_document(
        session, transcriber=_down, uploads_dir=tmp_path, preparer=_fake_preparer(1)
    )
    session.refresh(doc)
    assert doc.status == DocumentStatus.error
    assert "failed" in (doc.status_detail or "").lower()


def test_transcribe_pending_empty_text_sets_error(
    session: Session, tmp_path: Path
) -> None:
    doc = _audio_doc(session, tmp_path)
    tx.transcribe_pending_document(
        session,
        transcriber=lambda _p, _m: "   ",
        uploads_dir=tmp_path,
        preparer=_fake_preparer(1),
    )
    session.refresh(doc)
    assert doc.status == DocumentStatus.error


def test_transcribe_pending_missing_file_sets_error(
    session: Session, tmp_path: Path
) -> None:
    doc = _audio_doc(session, tmp_path)
    tx.audio_path_for(doc, tmp_path).unlink()  # simulate a lost upload
    tx.transcribe_pending_document(
        session, transcriber=lambda _p, _m: "x", uploads_dir=tmp_path
    )
    session.refresh(doc)
    assert doc.status == DocumentStatus.error
    assert "missing" in (doc.status_detail or "").lower()


def test_transcribe_pending_none_when_nothing_to_do(session: Session) -> None:
    assert tx.transcribe_pending_document(session, transcriber=lambda *_: "x") is None


def test_transcribe_once_noop_without_gemini_key(session: Session) -> None:
    # Default settings have no Gemini key → transcription can't run yet.
    assert transcribe_once(session) is None


def test_retrigger_transcription_resets_status(
    session: Session, tmp_path: Path
) -> None:
    doc = _audio_doc(session, tmp_path)
    doc.status = DocumentStatus.error
    doc.status_detail = "rate limited"
    session.commit()
    again = docsvc.retrigger_transcription(session, doc.id)
    assert again.status == DocumentStatus.transcribing
    assert again.status_detail is None


def test_retrigger_rejects_non_audio(session: Session, tmp_path: Path) -> None:
    subject = _subject(session)
    pdf = Document(
        subject_id=subject.id, filename="x.pdf", file_hash="h", source_type="pdf"
    )
    session.add(pdf)
    session.commit()
    with pytest.raises(docsvc.DocumentNotFoundError):
        docsvc.retrigger_transcription(session, pdf.id)


def test_audio_confirm_enqueues_generation_without_formula(
    session: Session, tmp_path: Path
) -> None:
    """Audio docs have no PDF page, so the formula stage must be skipped."""
    doc = _audio_doc(session, tmp_path)
    # Simulate a finished transcription.
    transcript = tmp_path / "t.md"
    transcript.write_text("## A\n\ntext", encoding="utf-8")
    doc.markdown_path = str(transcript)
    doc.status = DocumentStatus.uploaded
    session.commit()

    docsvc.confirm_structure(
        session,
        doc.id,
        chapters=[
            ChapterIn(
                title="Chapter",
                topics=[TopicIn(title="Topic")],
                queue_state=QueueLaneState.running,
            )
        ],
    )
    stages = set(session.scalars(select(QueueJob.stage)).all())
    assert QueueStage.notes in stages
    assert QueueStage.formula not in stages


# --- HTTP routing (shared in-memory DB via StaticPool) ----------------------


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


def test_http_upload_audio_starts_transcribing(
    client: TestClient, db_factory: sessionmaker
) -> None:
    with db_factory() as db:
        subject = Subject(name="Physics")
        db.add(subject)
        db.commit()
        subject_id = subject.id

    response = client.post(
        "/api/documents",
        data={"subject_id": str(subject_id)},
        files={"file": ("lecture.mp3", b"fake-audio", "audio/mpeg")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document"]["source_type"] == "audio"
    assert body["document"]["status"] == "transcribing"


def test_http_upload_rejects_unknown_type(
    client: TestClient, db_factory: sessionmaker
) -> None:
    with db_factory() as db:
        subject = Subject(name="Physics")
        db.add(subject)
        db.commit()
        subject_id = subject.id

    response = client.post(
        "/api/documents",
        data={"subject_id": str(subject_id)},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400  # not audio, not a PDF


def test_http_transcript_404_for_unknown(client: TestClient) -> None:
    assert client.get("/api/documents/999/transcript").status_code == 404


def test_http_retry_404_for_unknown(client: TestClient) -> None:
    assert client.post("/api/documents/999/transcribe/retry").status_code == 404
