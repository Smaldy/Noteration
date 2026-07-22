"""Schemas for the AI assistant sidebar chat (`/api/chat`)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatAttachmentOut(BaseModel):
    """One image/PDF attached to a turn (or an unsent draft)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str  # "image" | "pdf"
    filename: str
    content_type: str


class ChatMessageOut(BaseModel):
    """One turn of a chat session, as stored."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str  # "user" | "assistant"
    content: str
    # Which provider served an assistant turn (stamps the reply); None on user turns.
    provider: str | None
    created_at: datetime
    attachments: list[ChatAttachmentOut] = []


class ChatSendRequest(BaseModel):
    """Send one user message; omitting ``session_id`` starts a new session.

    ``provider`` pins the session's model selector choice (a provider name from
    the configured waterfall); ``None`` means the full cheapest-first waterfall.
    ``topic_id`` is the reference-topic chip: the topic whose stored material
    grounds the reply. Both are carried on every send and recorded on the
    session, so ``None`` clears them.

    ``request_id`` is the client's handle on this send, so the stop button can
    reach it (``POST /chat/stop``) before the reply is stored.
    """

    session_id: int | None = None
    message: str = Field(min_length=1, max_length=20_000)
    provider: str | None = None
    topic_id: int | None = None
    request_id: str | None = Field(default=None, max_length=64)
    # Ids from POST /chat/attachments, in display order. Already-sent ids are
    # ignored rather than rejected, so a retried send can't steal them.
    attachment_ids: list[int] = Field(default_factory=list, max_length=8)


class ChatAttachmentsAvailable(BaseModel):
    """Whether attachments can be sent with the configured providers."""

    available: bool


class ChatStopRequest(BaseModel):
    """Stop an in-flight send: its reply is discarded instead of stored."""

    request_id: str = Field(min_length=1, max_length=64)


class ChatStopResponse(BaseModel):
    """``stopped`` is False when the reply had already landed (nothing to stop).

    ``session_id`` is the session the stopped question went into: a stopped
    first send never delivers its response, so this is how the sidebar learns
    where to continue.
    """

    stopped: bool
    session_id: int | None = None


class ChatSendResponse(BaseModel):
    """The assistant's reply, plus the session it belongs to.

    ``closed`` is True when that reply was the assistant ending the
    conversation: the text is shown as normal, and the composer then locks.
    """

    session_id: int
    message: ChatMessageOut
    closed: bool = False


class ChatSessionSummary(BaseModel):
    """One history-list entry (no messages)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    provider: str | None
    updated_at: datetime


class ChatSessionOut(BaseModel):
    """A full session, messages included — reopening from history.

    ``topic_id``/``topic_title`` restore the reference chip; the title is
    resolved server-side so the sidebar needn't refetch the topic tree to
    label it.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    provider: str | None
    topic_id: int | None
    topic_title: str | None
    updated_at: datetime
    # Set when the assistant ended the conversation itself; reopening it from
    # history shows the transcript with a locked composer.
    closed_at: datetime | None = None
    messages: list[ChatMessageOut]
