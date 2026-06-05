"""Subject → Document/Chapter → Topic — the content hierarchy.

The Topic is the atomic unit of processing and the result transaction boundary.
``Chapter.subject_id`` is denormalized for query speed and must be kept
consistent with the parent document's subject on every write (see data-model.md).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base
from backend.db.types import UTCDateTime
from backend.models.enums import (
    DocumentMode,
    DocumentStatus,
    QueueLaneState,
    TopicPriority,
    TopicStatus,
)

if TYPE_CHECKING:
    from backend.models.content import MCQ, Flashcard, Note, SourcePage
    from backend.models.processing import QueueJob
    from backend.models.schedule import ScheduleEntry


def utcnow() -> datetime:
    """Timezone-aware UTC now — the default for all created/updated stamps."""
    return datetime.now(timezone.utc)


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    accent_color: Mapped[str | None] = mapped_column(default=None)
    exam_date: Mapped[date | None] = mapped_column(default=None)
    bookmarked: Mapped[bool] = mapped_column(default=False)
    # Per-subject queue lane state (Wave B): running / paused / overnight. The
    # lane is the unit the user pauses/resumes and puts in overnight mode.
    queue_state: Mapped[QueueLaneState] = mapped_column(
        SAEnum(QueueLaneState, native_enum=False), default=QueueLaneState.running
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    documents: Mapped[list[Document]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )
    # Read-only convenience over the denormalized FK. Chapters are owned and
    # cascade-deleted via Document (their structural parent), so this side stays
    # viewonly to avoid double cascade management and overlap warnings.
    chapters: Mapped[list[Chapter]] = relationship("Chapter", viewonly=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE")
    )
    filename: Mapped[str]
    file_hash: Mapped[str]  # cache key for markdown + page renders
    markdown_path: Mapped[str | None] = mapped_column(default=None)
    # "pdf" (default) or "audio". Audio documents store their uploaded file under
    # uploads/<hash>.<ext>, are transcribed to markdown (the transcript path lands
    # in markdown_path), then follow the same structure-review → queue → notes flow.
    # PDF-only stages (formula vision) are skipped for audio (no page to crop).
    source_type: Mapped[str] = mapped_column(default="pdf", server_default="pdf")
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, native_enum=False), default=DocumentStatus.uploaded
    )
    # Human-readable detail for the current status (e.g. a transcription rate-limit
    # "try again later" message). Null when there's nothing to say.
    status_detail: Mapped[str | None] = mapped_column(default=None)
    # study = full pipeline (notes + assessment); exam = assessment-only (the
    # dedicated Exam Prep section). Drives stage enqueue + generation prompt.
    mode: Mapped[DocumentMode] = mapped_column(
        SAEnum(DocumentMode, native_enum=False), default=DocumentMode.study
    )
    order_index: Mapped[int] = mapped_column(default=0)  # manual Library order
    uploaded_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    subject: Mapped[Subject] = relationship(back_populates="documents")
    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE")
    )  # denormalized; keep consistent with document.subject_id on write
    title: Mapped[str]
    order_index: Mapped[int] = mapped_column(default=0)
    # Per-chapter queue lane (Chapter Lanes): reuses the same lane states as the
    # subject lane, but a *chapter* defaults to ``paused`` — on confirm every
    # chapter starts paused and the user explicitly enables the ones to process,
    # so a 700-page book never burns free-tier quota on chapters not being studied.
    queue_state: Mapped[QueueLaneState] = mapped_column(
        SAEnum(QueueLaneState, native_enum=False),
        default=QueueLaneState.paused,
        server_default="paused",
    )
    # Outline-backed page range (1-indexed, inclusive). Set for books whose TOC
    # gives chapter spans; ``None`` for slide decks / headingless docs that follow
    # the existing whole-doc / proportional source-loading path unchanged.
    page_start: Mapped[int | None] = mapped_column(Integer, default=None)
    page_end: Mapped[int | None] = mapped_column(Integer, default=None)

    document: Mapped[Document] = relationship(back_populates="chapters")
    # Writable many-to-one so the denormalized subject_id is set on assignment;
    # no back_populates (the Subject side is viewonly).
    subject: Mapped[Subject] = relationship("Subject")
    topics: Mapped[list[Topic]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan"
    )


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE")
    )
    title: Mapped[str]
    priority: Mapped[TopicPriority] = mapped_column(
        SAEnum(TopicPriority, native_enum=False), default=TopicPriority.medium
    )
    status: Mapped[TopicStatus] = mapped_column(
        SAEnum(TopicStatus, native_enum=False), default=TopicStatus.queued
    )
    studied: Mapped[bool] = mapped_column(default=False)
    bookmarked: Mapped[bool] = mapped_column(default=False)
    order_index: Mapped[int] = mapped_column(default=0)

    chapter: Mapped[Chapter] = relationship(back_populates="topics")
    notes: Mapped[list[Note]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    mcqs: Mapped[list[MCQ]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    flashcards: Mapped[list[Flashcard]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    source_pages: Mapped[list[SourcePage]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    schedule_entries: Mapped[list[ScheduleEntry]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    queue_jobs: Mapped[list[QueueJob]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
