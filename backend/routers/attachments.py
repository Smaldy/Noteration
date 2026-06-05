"""Attachments router — serve and delete a topic's manual note attachments.

Uploads are created on the topics router (``POST /topics/{id}/attachments``); this
serves the stored file with its real mime and deletes an attachment.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.db.database import get_session
from backend.services import attachments as attachsvc

router = APIRouter(prefix="/attachments", tags=["attachments"])


@router.get("/{attachment_id}/file")
def get_attachment_file(
    attachment_id: int,
    session: Session = Depends(get_session),
) -> FileResponse:
    """Serve an attachment's bytes with its stored content type."""
    try:
        attachment = attachsvc.get_attachment(session, attachment_id)
    except attachsvc.AttachmentNotFoundError:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = attachsvc.attachment_path(attachment)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file missing")
    return FileResponse(
        path, media_type=attachment.content_type, filename=attachment.filename
    )


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: int,
    session: Session = Depends(get_session),
) -> Response:
    """Delete a topic attachment (removes the file if unreferenced)."""
    try:
        attachsvc.delete_attachment(session, attachment_id)
    except attachsvc.AttachmentNotFoundError:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
