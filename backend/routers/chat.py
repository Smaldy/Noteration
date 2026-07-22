"""Chat router — the AI assistant sidebar's HTTP surface (thin handler only)."""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.models.chat import ChatSession
from backend.schemas.chat import (
    ChatAttachmentOut,
    ChatAttachmentsAvailable,
    ChatSendRequest,
    ChatSendResponse,
    ChatSessionOut,
    ChatSessionSummary,
    ChatStopRequest,
    ChatStopResponse,
)
from backend.services import chat as chatsvc
from backend.services import chat_attachments

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
    name, 409 for a session the assistant closed, 503 when no provider can serve
    the reply right now.
    """
    try:
        chat, reply = chatsvc.send_message(
            session,
            message=payload.message,
            session_id=payload.session_id,
            provider=payload.provider,
            topic_id=payload.topic_id,
            request_id=payload.request_id,
            attachment_ids=payload.attachment_ids,
        )
    except chat_attachments.AttachmentsUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except chatsvc.ChatSessionNotFoundError:
        raise HTTPException(status_code=404, detail="Chat session not found")
    except chatsvc.ChatClosedError:
        raise HTTPException(
            status_code=409, detail="This conversation was closed. Start a new chat."
        )
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
    return ChatSendResponse(
        session_id=chat.id, message=reply, closed=chat.closed_at is not None
    )


@router.get("/attachments/available", response_model=ChatAttachmentsAvailable)
def attachments_available(
    session: Session = Depends(get_session),
) -> ChatAttachmentsAvailable:
    """Whether this install can accept attachments at all.

    The sidebar calls this to decide between an enabled paperclip and the "not
    available for this model" state, so the UI and the upload guard below are
    driven by the same rule rather than by a hardcoded provider name.
    """
    return ChatAttachmentsAvailable(available=chatsvc.attachments_supported(session))


@router.post("/attachments", response_model=ChatAttachmentOut, status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> ChatAttachmentOut:
    """Upload one image or PDF as a draft, to be sent with the next message.

    Returns the draft's id for ``ChatSendRequest.attachment_ids``. 400 for an
    unsupported/oversized file or a PDF with no extractable text, and 400 when
    no vision-capable provider is configured.
    """
    if not chatsvc.attachments_supported(session):
        raise HTTPException(
            status_code=400,
            detail="Attachments need a cloud model; not available for this model.",
        )
    data = await file.read()
    try:
        attachment = chat_attachments.upload_attachment(
            session,
            filename=file.filename or "attachment",
            content_type=file.content_type or "",
            data=data,
        )
    except chat_attachments.UnsupportedChatAttachmentError as exc:
        raise HTTPException(status_code=400, detail=f"Unsupported file: {exc}")
    except chat_attachments.PdfExtractionError as exc:
        raise HTTPException(status_code=400, detail=f"Could not read PDF: {exc}")
    return ChatAttachmentOut.model_validate(attachment)


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard_attachment(
    attachment_id: int, session: Session = Depends(get_session)
) -> Response:
    """Drop an unsent draft (removing a chip from the composer)."""
    chat_attachments.discard_draft(session, attachment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
