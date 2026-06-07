"""Note attachments — manual image/audio files a user attaches to a topic's notes.

User-only enrichment (never AI): the bytes are stored under
``cache/attachments/<hash><ext>`` (content-addressed, so re-uploading the same file
is a no-op) and a ``NoteAttachment`` row records the topic, kind, filename, and
content type so the file can be served back with the right mime. Deleting a topic
cascades its attachments; the file is removed only when no row still references it.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import NoteAttachment, Topic
from backend.paths import ATTACHMENTS_DIR  # sibling of uploads/ under the cache dir

# Cap an attachment at 25 MB — generous for a lecture photo or a short clip while
# keeping a single local file from ballooning the cache.
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


class TopicNotFoundError(LookupError):
    """Referenced topic does not exist."""


class AttachmentNotFoundError(LookupError):
    """Referenced attachment does not exist."""


class UnsupportedAttachmentError(ValueError):
    """The file isn't an accepted image/audio type, is empty, or too large."""


def _kind_for(content_type: str) -> str:
    """Map a content type to "image"/"audio", or reject it."""
    main = (content_type or "").split("/", 1)[0].lower()
    if main in {"image", "audio"}:
        return main
    raise UnsupportedAttachmentError(content_type)


def attachment_path(attachment: NoteAttachment) -> Path:
    """Where an attachment's bytes live: cache/attachments/<hash><ext>."""
    ext = Path(attachment.filename).suffix.lower()
    return ATTACHMENTS_DIR / f"{attachment.file_hash}{ext}"


def attachment_url(attachment: NoteAttachment) -> str:
    """The API path that serves this attachment's file."""
    return f"/api/attachments/{attachment.id}/file"


def add_attachment(
    session: Session,
    topic_id: int,
    *,
    filename: str,
    content_type: str,
    data: bytes,
) -> NoteAttachment:
    """Persist an uploaded image/audio file and attach it to a topic."""
    if not data:
        raise UnsupportedAttachmentError("empty file")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise UnsupportedAttachmentError("file too large")
    kind = _kind_for(content_type)
    if session.get(Topic, topic_id) is None:
        raise TopicNotFoundError(topic_id)

    file_hash = _persist(data, filename)
    attachment = NoteAttachment(
        topic_id=topic_id,
        kind=kind,
        filename=filename,
        content_type=content_type,
        file_hash=file_hash,
    )
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment


def get_attachment(session: Session, attachment_id: int) -> NoteAttachment:
    """Return an attachment row or raise ``AttachmentNotFoundError``."""
    attachment = session.get(NoteAttachment, attachment_id)
    if attachment is None:
        raise AttachmentNotFoundError(attachment_id)
    return attachment


def delete_attachment(session: Session, attachment_id: int) -> None:
    """Delete an attachment row, removing its file if nothing else references it."""
    attachment = session.get(NoteAttachment, attachment_id)
    if attachment is None:
        raise AttachmentNotFoundError(attachment_id)
    path = attachment_path(attachment)
    file_hash = attachment.file_hash
    session.delete(attachment)
    session.commit()
    # Remove the bytes only when no remaining attachment shares this content hash
    # (uploads are content-addressed, so two topics can point at the same file).
    still_used = session.scalar(
        select(func.count())
        .select_from(NoteAttachment)
        .where(NoteAttachment.file_hash == file_hash)
    )
    if not still_used and path.is_file():
        path.unlink()


def _persist(data: bytes, filename: str) -> str:
    """Write bytes under cache/attachments/<hash><ext> (idempotent, atomic)."""
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    file_hash = hashlib.sha256(data).hexdigest()
    ext = Path(filename).suffix.lower()
    dest = ATTACHMENTS_DIR / f"{file_hash}{ext}"
    if not dest.exists():
        tmp = ATTACHMENTS_DIR / f".{file_hash}.{os.getpid()}.tmp"
        tmp.write_bytes(data)
        os.replace(tmp, dest)
    return file_hash
