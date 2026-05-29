"""Document service + HTTP tests (Phase 6b): upload/ingest and structure detect."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.db.database import Base, get_session
from backend.main import app
from backend.models import Document, Subject
from backend.services import documents as docsvc
from backend.services.pipeline.ingestion import IngestionResult

_MINIMAL_PDF = b"%PDF-1.4\n%fake bytes for tests\n"


def _fake_ingest_factory(markdown_path: Path, *, pages: int = 2, scanned: bool = False):
    def _fake(pdf_path: Path) -> IngestionResult:
        return IngestionResult(
            file_hash="deadbeef",
            markdown=markdown_path.read_text(encoding="utf-8"),
            markdown_path=markdown_path,
            page_image_paths=[Path(f"p{i}.png") for i in range(pages)],
            page_count=pages,
            is_scanned=scanned,
            from_cache=False,
        )

    return _fake


# --- service unit tests (existing in-memory `session` fixture) ---------------


def test_create_document_persists_row(session: Session, tmp_path: Path) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# Chapter 1\n## Topic\n", encoding="utf-8")
    subject = Subject(name="Physics")
    session.add(subject)
    session.commit()

    document, result = docsvc.create_document(
        session,
        subject_id=subject.id,
        filename="lec.pdf",
        data=_MINIMAL_PDF,
        ingest_fn=_fake_ingest_factory(md),
        uploads_dir=tmp_path / "uploads",
    )

    assert document.id is not None
    assert document.file_hash == "deadbeef"
    assert document.markdown_path == str(md)
    assert result.page_count == 2
    assert (tmp_path / "uploads").exists()


def test_create_document_rejects_non_pdf(session: Session, tmp_path: Path) -> None:
    subject = Subject(name="Physics")
    session.add(subject)
    session.commit()
    with pytest.raises(docsvc.InvalidPDFError):
        docsvc.create_document(
            session,
            subject_id=subject.id,
            filename="x.txt",
            data=b"not a pdf",
            ingest_fn=_fake_ingest_factory(tmp_path / "unused.md"),
            uploads_dir=tmp_path / "uploads",
        )


def test_create_document_unknown_subject(session: Session, tmp_path: Path) -> None:
    with pytest.raises(docsvc.SubjectNotFoundError):
        docsvc.create_document(
            session,
            subject_id=999,
            filename="x.pdf",
            data=_MINIMAL_PDF,
            ingest_fn=_fake_ingest_factory(tmp_path / "unused.md"),
            uploads_dir=tmp_path / "uploads",
        )


def test_detect_for_document_reads_markdown(session: Session, tmp_path: Path) -> None:
    md = tmp_path / "doc.md"
    md.write_text("# A\n## A1\n# B\n", encoding="utf-8")
    subject = Subject(name="Physics")
    session.add(subject)
    session.commit()
    document = Document(
        subject_id=subject.id, filename="f.pdf", file_hash="h", markdown_path=str(md)
    )
    session.add(document)
    session.commit()

    structure = docsvc.detect_for_document(session, document.id)
    assert [c.title for c in structure.chapters] == ["A", "B"]


def test_detect_for_document_missing_markdown(session: Session, tmp_path: Path) -> None:
    subject = Subject(name="Physics")
    session.add(subject)
    session.commit()
    document = Document(
        subject_id=subject.id,
        filename="f.pdf",
        file_hash="h",
        markdown_path=str(tmp_path / "gone.md"),
    )
    session.add(document)
    session.commit()
    with pytest.raises(docsvc.MarkdownUnavailableError):
        docsvc.detect_for_document(session, document.id)


# --- HTTP tests (shared in-memory DB via StaticPool) ------------------------


@pytest.fixture
def db_factory() -> Generator[sessionmaker, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # one shared in-memory connection across threads
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


def _make_real_pdf(path: Path) -> bytes:
    fitz = __import__("fitz")
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "# Kinematics")
    doc.new_page().insert_text((72, 72), "Velocity is the rate of change of position.")
    doc.save(str(path))
    doc.close()
    return path.read_bytes()


def test_upload_and_detect_end_to_end(
    client: TestClient, db_factory: sessionmaker, tmp_path: Path
) -> None:
    with db_factory() as db:
        subject = Subject(name="Physics")
        db.add(subject)
        db.commit()
        subject_id = subject.id

    pdf_bytes = _make_real_pdf(tmp_path / "real.pdf")
    response = client.post(
        "/api/documents",
        data={"subject_id": str(subject_id)},
        files={"file": ("real.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["page_count"] == 2
    assert body["is_scanned"] is False
    document_id = body["document"]["id"]
    assert body["document"]["status"] == "uploaded"

    structure = client.get(f"/api/documents/{document_id}/structure")
    assert structure.status_code == 200
    assert structure.json()["needs_manual"] is False


def test_upload_non_pdf_returns_400(client: TestClient, db_factory: sessionmaker) -> None:
    with db_factory() as db:
        subject = Subject(name="Physics")
        db.add(subject)
        db.commit()
        subject_id = subject.id

    response = client.post(
        "/api/documents",
        data={"subject_id": str(subject_id)},
        files={"file": ("notes.txt", b"just text", "text/plain")},
    )
    assert response.status_code == 400


def test_upload_unknown_subject_returns_404(
    client: TestClient, tmp_path: Path
) -> None:
    pdf_bytes = _make_real_pdf(tmp_path / "real.pdf")
    response = client.post(
        "/api/documents",
        data={"subject_id": "999"},
        files={"file": ("real.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 404


def test_structure_unknown_document_returns_404(client: TestClient) -> None:
    assert client.get("/api/documents/999/structure").status_code == 404


def _upload_real_doc(client: TestClient, db_factory: sessionmaker, tmp_path: Path) -> int:
    with db_factory() as db:
        subject = Subject(name="Physics")
        db.add(subject)
        db.commit()
        subject_id = subject.id
    pdf_bytes = _make_real_pdf(tmp_path / "real.pdf")
    response = client.post(
        "/api/documents",
        data={"subject_id": str(subject_id)},
        files={"file": ("real.pdf", pdf_bytes, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["document"]["id"]


def test_confirm_structure_http_flow(
    client: TestClient, db_factory: sessionmaker, tmp_path: Path
) -> None:
    document_id = _upload_real_doc(client, db_factory, tmp_path)

    payload = {
        "exam_date": "2026-06-20",
        "chapters": [
            {
                "title": "Chapter 1",
                "topics": [
                    {"title": "Kinematics", "priority": "exam_critical"},
                    {"title": "Appendix", "priority": "skip"},
                ],
            }
        ],
    }
    response = client.post(f"/api/documents/{document_id}/structure", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body == {
        "document_id": document_id,
        "chapters_created": 1,
        "topics_created": 2,
        "topics_enqueued": 1,
    }

    # Re-confirming the same document is a conflict.
    again = client.post(f"/api/documents/{document_id}/structure", json=payload)
    assert again.status_code == 409


def test_confirm_empty_chapters_is_422(
    client: TestClient, db_factory: sessionmaker, tmp_path: Path
) -> None:
    document_id = _upload_real_doc(client, db_factory, tmp_path)
    response = client.post(
        f"/api/documents/{document_id}/structure", json={"chapters": []}
    )
    assert response.status_code == 422
