"""Chat router — the AI assistant sidebar's HTTP surface (thin handler only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models.chat import ChatSession
from backend.schemas.chat import (
    ChatSendRequest,
    ChatSendResponse,
    ChatSessionOut,
    ChatSessionSummary,
    ChatStopRequest,
    ChatStopResponse,
)
from backend.services import chat as chatsvc

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatSendResponse)
def send_message(
    payload: ChatSendRequest,
    session: Session = Depends(get_session),
) -> ChatSendResponse:
    """Send one user message and return the assistant's reply.

    Omitting ``session_id`` starts a new session (its id comes back in the
    response). ``topic_id`` pins the reference topic whose material grounds the
    reply. 404 for an unknown session or topic, 400 for an unknown provider
    name, 503 when no provider can serve the reply right now.
    """
    try:
        chat, reply = chatsvc.send_message(
            session,
            message=payload.message,
            session_id=payload.session_id,
            provider=payload.provider,
            topic_id=payload.topic_id,
            request_id=payload.request_id,
        )
    except chatsvc.ChatSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Chat session not found")
    except chatsvc.TopicNotFoundError:
        raise HTTPException(status_code=404, detail="Topic not found")
    except chatsvc.UnknownProviderError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {exc}")
    except chatsvc.ChatStoppedError:
        # The client has already walked away from this response (it aborted the
        # request when the user pressed stop); the status is for the record.
        raise HTTPException(status_code=409, detail="Reply stopped")
    except chatsvc.ChatUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return ChatSendResponse(session_id=chat.id, message=reply)


@router.post("/stop", response_model=ChatStopResponse)
def stop_reply(payload: ChatStopRequest) -> ChatStopResponse:
    """Stop an in-flight send so its reply is discarded instead of stored.

    A provider call can't be interrupted, so this is honest about what it does:
    the answer is thrown away when it arrives. ``stopped: false`` means the
    reply had already been stored and there was nothing left to stop. The
    session id comes back so a stopped first send still tells the client which
    session its question is in.
    """
    stopped, session_id = chatsvc.stop_request(payload.request_id)
    return ChatStopResponse(stopped=stopped, session_id=session_id)


@router.get("/sessions", response_model=list[ChatSessionSummary])
def list_sessions(session: Session = Depends(get_session)) -> list[ChatSession]:
    """The history list: the last 5 sessions, newest first."""
    return chatsvc.list_sessions(session)


@router.get("/sessions/{session_id}", response_model=ChatSessionOut)
def get_chat_session(
    session_id: int,
    session: Session = Depends(get_session),
) -> ChatSession:
    """One session with its full transcript (reopen from history)."""
    try:
        return chatsvc.get_chat_session(session, session_id)
    except chatsvc.ChatSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Chat session not found")


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Delete a session and its messages."""
    try:
        chatsvc.delete_session(session, session_id)
    except chatsvc.ChatSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
