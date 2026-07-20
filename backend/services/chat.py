"""Assistant chat service — the one grounded-chat engine behind the AI sidebar.

Builds a bounded prompt from the session's stored turns, calls the provider
waterfall (or the single provider the sidebar pinned), and appends the reply.
Reuses the existing ``providers/`` factory wholesale — no provider code here.

SQLite is single-writer, so the user turn is committed *before* the provider
call and the assistant turn in a fresh transaction after it; no write lock is
ever held across the network round-trip.
"""

from __future__ import annotations

import threading
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models.chat import ChatMessage, ChatSession
from backend.models.hierarchy import Topic, utcnow
from backend.services.pipeline.generation import (
    field_profile,
    language_directive,
)
from backend.services.providers.base import AllProvidersExhausted, ProviderError
from backend.services.providers.factory import build_waterfall_from_settings
from backend.services.providers.waterfall import Waterfall
from backend.services.retrieval import TopicContext, build_topic_context
from backend.services.settings import get_settings

# Reply ceiling: a chat answer, not an essay. Long-form output belongs to the
# generation pipeline; the sidebar's job is focused answers.
REPLY_MAX_TOKENS = 2048

# Prompt bounds: the most recent turns, capped by count and by total characters
# (oldest dropped first).
MAX_HISTORY_MESSAGES = 20
MAX_HISTORY_CHARS = 24_000

# A pinned topic's retrieved material is *taken out of* the history budget, not
# added on top: the prompt ceiling that already suits the smallest local model
# in the waterfall stays exactly where it is. This floor keeps a large extract
# from starving the conversation itself — the last few turns always fit.
MIN_HISTORY_CHARS = 8_000

TITLE_MAX_CHARS = 60

# History cap: the last 5 sessions. Creating a 6th evicts the oldest, and the
# list endpoint never returns more — the count-based default retention.
MAX_SESSIONS = 5

# Time-based retention windows (Settings.chat_retention opt-ins). Sessions
# whose *last activity* is older than the window are expired; an active thread
# keeps renewing its updated_at. "on_close" purges everything, but only at
# startup — the previous run's chats, never the one in progress.
RETENTION_WINDOWS: dict[str, timedelta] = {
    "after_1_hour": timedelta(hours=1),
    "after_1_day": timedelta(days=1),
}


class ChatSessionNotFoundError(LookupError):
    """Referenced chat session does not exist."""


class UnknownProviderError(ValueError):
    """The requested provider name is not part of the configured waterfall."""


class TopicNotFoundError(LookupError):
    """The topic pinned as the session's reference does not exist."""


class ChatUnavailableError(RuntimeError):
    """No provider could serve the reply right now (limits or hard failures)."""


class ChatStoppedError(RuntimeError):
    """The user stopped this reply while it was being generated."""


# Seam for tests: monkeypatch to inject a fake waterfall.
_build_waterfall = build_waterfall_from_settings

# In-flight sends, and the ones the user stopped. A provider call can't be
# interrupted mid-flight, so "stop" is enforced at the *storage* boundary: the
# reply that lands after a stop is discarded instead of appended. Without this
# the client's abort would be a lie — the turn would still be persisted and
# reappear the next time the session was opened.
#
# Keyed by a client-supplied request id (not a session id) because a session's
# very first send has no id yet, and that is exactly when a slow cold start
# makes the user reach for stop. Process-local by design: this is a local-first
# single-process app, and a restart cancels everything in flight anyway.
_inflight: dict[str, int] = {}  # request id → the session it is answering into
_stopped: set[str] = set()
_stop_lock = threading.Lock()


def stop_request(request_id: str) -> tuple[bool, int | None]:
    """Mark an in-flight send as stopped: ``(stopped, session_id)``.

    The session id goes back to the caller because a stopped *first* send never
    delivers its response — without this the sidebar would not learn which
    session its own question landed in, and the next message would silently
    start a second one.

    An unknown id stops nothing (the reply was already stored) and is not an
    error; ignoring it is also what keeps these maps from growing.
    """
    with _stop_lock:
        session_id = _inflight.get(request_id)
        if session_id is None:
            return False, None
        _stopped.add(request_id)
        return True, session_id


def _finish_request(request_id: str | None) -> bool:
    """Retire an in-flight send; True if the user stopped it while it ran."""
    if request_id is None:
        return False
    with _stop_lock:
        _inflight.pop(request_id, None)
        stopped = request_id in _stopped
        _stopped.discard(request_id)
    return stopped


def send_message(
    session: Session,
    *,
    message: str,
    session_id: int | None = None,
    provider: str | None = None,
    topic_id: int | None = None,
    request_id: str | None = None,
) -> tuple[ChatSession, ChatMessage]:
    """Append a user turn, get the assistant's reply, and store both.

    ``topic_id`` is the session's reference topic (the sidebar's chip): its
    stored material is retrieved and grounds the reply. Like ``provider``, it is
    carried on every send and recorded on the session, so removing the chip
    (``None``) unpins it and reopening the session restores it.

    ``request_id`` lets the sidebar's stop button reach this send: if it was
    stopped while the provider was working, the reply is thrown away rather than
    stored, and ``ChatStoppedError`` is raised.

    Returns ``(chat_session, assistant_message)``. Raises
    ``ChatSessionNotFoundError`` / ``UnknownProviderError`` / ``TopicNotFoundError``
    for bad input, ``ChatStoppedError`` when the user stopped the reply, and
    ``ChatUnavailableError`` when every provider is exhausted or failing.
    """
    settings = get_settings(session)
    waterfall = _build_waterfall(settings)
    if provider is not None:
        # Pin the selector's choice — validated against the *configured*
        # waterfall, never a hardcoded provider list.
        pinned = [p for p in waterfall.providers if p.name == provider]
        if not pinned:
            raise UnknownProviderError(provider)
        waterfall = Waterfall(pinned)
    if topic_id is not None and session.get(Topic, topic_id) is None:
        raise TopicNotFoundError(topic_id)

    chat = _load_or_create(session, session_id, message, provider, topic_id)
    is_new = chat.id is None
    chat.messages.append(ChatMessage(role="user", content=message))
    chat.updated_at = utcnow()
    if is_new:
        # Keep-last-5 eviction: a new session pushes the oldest one out.
        _evict_over_cap(session, keep=chat)
    # Commit the user turn now so no write lock spans the provider call.
    session.commit()

    # Retrieval reads the *committed* state and holds no lock across the call.
    context = (
        build_topic_context(session, chat.topic_id, query=message)
        if chat.topic_id is not None
        else None
    )
    prompt = _build_prompt(chat.messages, settings, context)
    if request_id is not None:
        # Registered only now, once the user turn is committed and the session
        # has an id to hand back to a stop.
        with _stop_lock:
            _inflight[request_id] = chat.id
    stopped = False
    try:
        result = waterfall.generate(prompt, max_tokens=REPLY_MAX_TOKENS)
    except AllProvidersExhausted as exc:
        raise ChatUnavailableError(exc.reason or "all providers exhausted") from exc
    except ProviderError as exc:
        raise ChatUnavailableError(str(exc)) from exc
    finally:
        # Cleanup only — a raise here would mask a provider failure that raced
        # the stop. The stop is acted on below, once the call has come back.
        stopped = _finish_request(request_id)

    if stopped:
        # The user is no longer waiting for this answer, so it is never stored.
        # The user turn stays (they did say it), exactly as when every provider
        # is exhausted.
        raise ChatStoppedError(request_id or "")

    reply = ChatMessage(
        role="assistant", content=result.text.strip(), provider=result.provider
    )
    chat.messages.append(reply)
    chat.updated_at = utcnow()
    session.commit()
    return chat, reply


def list_sessions(session: Session) -> list[ChatSession]:
    """The history list: the last ``MAX_SESSIONS`` sessions, newest first."""
    return list(
        session.execute(
            select(ChatSession)
            .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
            .limit(MAX_SESSIONS)
        ).scalars()
    )


def get_chat_session(session: Session, session_id: int) -> ChatSession:
    """Fetch one session with its messages. Raises if missing."""
    chat = session.execute(
        select(ChatSession)
        .where(ChatSession.id == session_id)
        .options(selectinload(ChatSession.messages))
    ).scalar_one_or_none()
    if chat is None:
        raise ChatSessionNotFoundError(session_id)
    return chat


def delete_session(session: Session, session_id: int) -> None:
    """Delete a session (messages cascade). Raises if missing."""
    chat = session.get(ChatSession, session_id)
    if chat is None:
        raise ChatSessionNotFoundError(session_id)
    session.delete(chat)
    session.commit()


def cleanup_sessions(session: Session, *, at_startup: bool = False) -> int:
    """Enforce the time-based retention opt-ins; return sessions deleted.

    Called by the queue worker at startup (``at_startup=True``, which is the
    only moment "on_close" may purge — it removes the *previous* run's chats)
    and periodically while running (time windows only). The "keep_last_5"
    default needs no pass here: the cap is enforced on session creation.
    """
    retention = get_settings(session).chat_retention
    if retention == "on_close":
        if not at_startup:
            return 0
        stale = list(session.execute(select(ChatSession)).scalars())
    elif retention in RETENTION_WINDOWS:
        cutoff = utcnow() - RETENTION_WINDOWS[retention]
        stale = list(
            session.execute(
                select(ChatSession).where(ChatSession.updated_at < cutoff)
            ).scalars()
        )
    else:
        return 0
    for chat in stale:
        session.delete(chat)
    if stale:
        session.commit()
    return len(stale)


def _evict_over_cap(session: Session, *, keep: ChatSession) -> None:
    """Delete the oldest sessions beyond ``MAX_SESSIONS``.

    Runs inside the user-turn transaction of the send that created ``keep``
    (autoflush puts the new row in the ordering); ``keep`` itself is never
    evicted, whatever its timestamp.
    """
    stale = session.execute(
        select(ChatSession)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc())
        .offset(MAX_SESSIONS)
    ).scalars()
    for chat in stale:
        if chat is not keep:
            session.delete(chat)


def _load_or_create(
    session: Session,
    session_id: int | None,
    first_message: str,
    provider: str | None,
    topic_id: int | None,
) -> ChatSession:
    if session_id is not None:
        chat = session.get(ChatSession, session_id)
        if chat is None:
            raise ChatSessionNotFoundError(session_id)
        # Selector and reference chip are per-session but changeable mid-thread;
        # remember the latest choice so a reopened session restores it.
        chat.provider = provider
        chat.topic_id = topic_id
        return chat
    # A whitespace-only message passes min_length but strips to nothing.
    first_line = first_message.strip().splitlines() or [""]
    title = first_line[0][:TITLE_MAX_CHARS]
    chat = ChatSession(title=title, provider=provider, topic_id=topic_id)
    session.add(chat)
    return chat


def _build_prompt(
    messages: list[ChatMessage],
    settings,  # noqa: ANN001
    context: TopicContext | None = None,
) -> str:
    """Preamble + reference material + the bounded transcript, ending on the cue."""
    profile = field_profile(settings.study_field)
    preamble = (
        f"You are {profile.persona} inside Noteration, a study app. Answer the "
        "student's questions clearly and accurately in Markdown (with $LaTeX$ "
        "for math). Be concise for simple questions and thorough for hard ones. "
        "If you are unsure, say so instead of inventing facts."
        f"{language_directive(settings.language)}"
    )

    reference = _reference_block(context) if context else ""
    # The retrieved material spends the history's budget rather than extending
    # the prompt. The floor only applies when there *is* material to make room
    # for, and never raises the cap above MAX_HISTORY_CHARS.
    history_chars = MAX_HISTORY_CHARS
    if reference:
        history_chars = max(
            MAX_HISTORY_CHARS - len(reference),
            min(MIN_HISTORY_CHARS, MAX_HISTORY_CHARS),
        )

    recent = messages[-MAX_HISTORY_MESSAGES:]
    lines: list[str] = []
    total = 0
    # Walk newest-first so the character cap drops the *oldest* turns.
    for msg in reversed(recent):
        speaker = "Student" if msg.role == "user" else "Assistant"
        line = f"{speaker}: {msg.content}"
        if lines and total + len(line) > history_chars:
            break
        lines.append(line)
        total += len(line)
    transcript = "\n\n".join(reversed(lines))
    return f"{preamble}\n{reference}\n# Conversation\n{transcript}\n\nAssistant:"


def _reference_block(context: TopicContext) -> str:
    """The pinned topic's material, framed so the model knows what it is."""
    instructions = (
        f"\n# Reference topic: {context.path}\n"
        "The student pinned this topic as the reference for this conversation. "
        "Ground your answer in the material below and prefer its wording and "
        "notation. Where the material is silent, say so plainly, then answer "
        "from general knowledge. A [...] marks material left out for length."
    )
    if not context.extract:
        # A topic whose content hasn't been generated yet: the path alone still
        # tells the model what the student is studying, which is worth having.
        return f"{instructions}\n(This topic has no study material yet.)\n"
    return f"{instructions}\n\n{context.extract}\n"
