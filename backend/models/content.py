"""Per-topic generated study content: Note, Formula, MCQ, Flashcard, SourcePage."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base
from backend.db.types import UTCDateTime
from backend.models.enums import FormulaState
from backend.models.hierarchy import utcnow

if TYPE_CHECKING:
    from backend.models.hierarchy import Topic


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    content_md: Mapped[str] = mapped_column(default="")
    is_manual: Mapped[bool] = mapped_column(default=False)
    locked: Mapped[bool] = mapped_column(default=False)
    # Set true when notes are regenerated and assessment not yet re-run.
    stale: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    topic: Mapped[Topic] = relationship(back_populates="notes")
    formulas: Mapped[list[Formula]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )


class Formula(Base):
    __tablename__ = "formulas"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id", ondelete="CASCADE"))
    latex: Mapped[str]  # vision-model transcription
    state: Mapped[FormulaState] = mapped_column(
        SAEnum(FormulaState, native_enum=False), default=FormulaState.reconstructed
    )
    confidence: Mapped[float | None] = mapped_column(default=None)  # low surfaces first
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)

    note: Mapped[Note] = relationship(back_populates="formulas")


class MCQ(Base):
    __tablename__ = "mcqs"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    question: Mapped[str]
    options: Mapped[list[str]] = mapped_column(JSON, default=list)
    correct_index: Mapped[int] = mapped_column(default=0)
    explanation: Mapped[str] = mapped_column(default="")
    is_manual: Mapped[bool] = mapped_column(default=False)

    topic: Mapped[Topic] = relationship(back_populates="mcqs")


class Flashcard(Base):
    """SM-2 spaced-repetition state lives on the card."""

    __tablename__ = "flashcards"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    front: Mapped[str]
    back: Mapped[str]
    is_manual: Mapped[bool] = mapped_column(default=False)
    ease_factor: Mapped[float] = mapped_column(default=2.5)
    interval: Mapped[int] = mapped_column(default=0)  # days until next review
    repetitions: Mapped[int] = mapped_column(default=0)  # consecutive correct count
    due_date: Mapped[date | None] = mapped_column(default=None)

    topic: Mapped[Topic] = relationship(back_populates="flashcards")


class SourcePage(Base):
    __tablename__ = "source_pages"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id", ondelete="CASCADE"))
    page_number: Mapped[int]
    image_path: Mapped[str]  # cached rendered page (for formula crops)

    topic: Mapped[Topic] = relationship(back_populates="source_pages")
