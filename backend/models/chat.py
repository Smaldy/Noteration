"""Assistant chat sessions: ChatSession + ChatMessage.

Backs the AI sidebar (one grounded-chat engine, several entry points). Sessions
are table-backed from the start so history/retention (Step 2) build on the same
rows the shell writes. Messages are child rows, not a JSON blob, so appending a
turn never rewrites the whole transcript.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base
from backend.db.types import UTCDateTime
from backend.models.hierarchy import utcnow

if TYPE_CHECKING:
    from backend.models.hierarchy import Topic


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # First user message, truncated — the label shown in the history list.
    title: Mapped[str] = mapped_column(default="")
    # Provider pinned by the sidebar's model selector; None = the full waterfall.
    provider: Mapped[str | None] = mapped_column(default=None)
    # The reference topic pinned to this session (the sidebar's chip): its stored
    # material grounds every reply. SET NULL rather than CASCADE — deleting a
    # topic must drop the chip, never the conversation about it.
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    messages: Mapped[list[ChatMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )
    topic: Mapped[Topic | None] = relationship("Topic")

    @property
    def topic_title(self) -> str | None:
        """The chip's label — resolved here so reopening a session restores it."""
        return self.topic.title if self.topic else None


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    role: Mapped[str]  # "user" | "assistant"
    content: Mapped[str] = mapped_column(default="")
    # Which provider actually served an assistant turn (None on user turns).
    provider: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    session: Mapped[ChatSession] = relationship(back_populates="messages")
