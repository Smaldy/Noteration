"""Overnight batch upload — many PDFs auto-detected, auto-confirmed, backgrounded.

Uses a fake ingest that writes real per-file markdown so the (unmodified)
detection + confirm services run for real; only the PDF→markdown step is faked.
"""

from pathlib import Path

import pytest

from backend.models import Subject
from backend.models.enums import DocumentStatus, QueueLaneState, TopicStatus
from backend.models.hierarchy import Topic
from backend.services import documents as docsvc
from backend.services.pipeline.ingestion import IngestionResult

_MINIMAL_PDF = b"%PDF-1.4\n%fake\n"


def _fake_ingest_factory(tmp_path: Path):
    """Fake ingest: distinct hash + markdown file per call (keyed by content)."""

    def _fake(pdf_path: Path) -> IngestionResult:
        data = pdf_path.read_bytes()
        key = str(abs(hash(data)) % 10_000)
        md = tmp_path / f"doc-{key}.md"
        md.write_text(f"# Chapter {key}\n## Topic A\n## Topic B\n", encoding="utf-8")
        return IngestionResult(
            file_hash=key,
            markdown=md.read_text(encoding="utf-8"),
            markdown_path=md,
            page_image_paths=[],
            page_count=2,
            is_scanned=False,
            from_cache=False,
        )

    return _fake


def _files(*names: str) -> list[tuple[str, bytes]]:
    # Distinct bytes per file so the fake ingest gives each its own hash/markdown.
    return [(name, _MINIMAL_PDF + name.encode()) for name in names]


def test_batch_confirms_every_pdf_and_backgrounds_the_lane(session, tmp_path):
    subject = Subject(name="Physics")
    session.add(subject)
    session.commit()

    result = docsvc.batch_process_overnight(
        session,
        subject_id=subject.id,
        files=_files("a.pdf", "b.pdf", "c.pdf"),
        uploads_dir=tmp_path,
        ingest_fn=_fake_ingest_factory(tmp_path),
    )

    assert result.documents_ok == 3
    assert all(item.ok for item in result.items)
    assert result.topics_enqueued == 6  # 2 topics per doc, all enqueued
    # The whole subject lane is now overnight (drains in the background).
    session.refresh(subject)
    assert subject.queue_state is QueueLaneState.overnight
    # Every topic is queued for generation, no manual review needed.
    topics = session.query(Topic).all()
    assert len(topics) == 6
    assert all(t.status is TopicStatus.queued for t in topics)


def test_batch_skips_a_bad_pdf_but_finishes_the_rest(session, tmp_path):
    subject = Subject(name="Physics")
    session.add(subject)
    session.commit()

    files = [
        ("good.pdf", _MINIMAL_PDF + b"good"),
        ("broken.txt", b"not a pdf at all"),  # no %PDF magic
        ("good2.pdf", _MINIMAL_PDF + b"good2"),
    ]
    result = docsvc.batch_process_overnight(
        session,
        subject_id=subject.id,
        files=files,
        uploads_dir=tmp_path,
        ingest_fn=_fake_ingest_factory(tmp_path),
    )

    assert result.documents_ok == 2
    bad = next(i for i in result.items if i.filename == "broken.txt")
    assert not bad.ok and bad.error == "not_a_pdf"
    # The good files still processed and the lane still went overnight.
    session.refresh(subject)
    assert subject.queue_state is QueueLaneState.overnight
    assert result.topics_enqueued == 4


def test_batch_headingless_pdf_still_yields_one_topic(session, tmp_path):
    """A PDF with no detectable structure must not be dropped: it collapses to
    a single whole-document topic (nobody is there to define a tree)."""

    def _headingless_ingest(pdf_path: Path) -> IngestionResult:
        md = tmp_path / "plain.md"
        md.write_text("plain prose with no headings whatsoever\n", encoding="utf-8")
        return IngestionResult(
            file_hash="plainhash",
            markdown=md.read_text(encoding="utf-8"),
            markdown_path=md,
            page_image_paths=[],
            page_count=1,
            is_scanned=False,
            from_cache=False,
        )

    subject = Subject(name="Physics")
    session.add(subject)
    session.commit()
    # A PDF must exist in uploads for the detection fallback to read.
    (tmp_path / "plainhash.pdf").write_bytes(_MINIMAL_PDF)

    result = docsvc.batch_process_overnight(
        session,
        subject_id=subject.id,
        files=[("lecture.pdf", _MINIMAL_PDF)],
        uploads_dir=tmp_path,
        ingest_fn=_headingless_ingest,
    )
    assert result.documents_ok == 1
    assert result.topics_enqueued >= 1
    topic = session.query(Topic).first()
    assert topic is not None


def test_batch_unknown_subject(session, tmp_path):
    with pytest.raises(docsvc.SubjectNotFoundError):
        docsvc.batch_process_overnight(
            session,
            subject_id=999,
            files=_files("a.pdf"),
            uploads_dir=tmp_path,
            ingest_fn=_fake_ingest_factory(tmp_path),
        )


def test_batch_document_is_processing_not_uploaded(session, tmp_path):
    subject = Subject(name="Physics")
    session.add(subject)
    session.commit()
    docsvc.batch_process_overnight(
        session,
        subject_id=subject.id,
        files=_files("a.pdf"),
        uploads_dir=tmp_path,
        ingest_fn=_fake_ingest_factory(tmp_path),
    )
    from backend.models import Document

    doc = session.query(Document).first()
    assert doc.status is DocumentStatus.processing  # auto-confirmed, no review
