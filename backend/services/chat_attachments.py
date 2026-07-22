"""Chat attachments — images and PDFs the user attaches to an AI sidebar turn.

The two kinds take deliberately different routes to the model:

- **image** — stored as bytes and handed to the provider as a real image part on
  every turn (``Provider.generate(images=...)``), so the model actually looks at
  the picture. Requires a vision-capable provider.
- **pdf** — converted to markdown ONCE here at upload, via the same markitdown
  backend the ingestion pipeline uses, and only the text is kept. A study PDF is
  mostly words, so text costs a fraction of the tokens a re-sent file would and
  the cost is paid once rather than per turn.

Both kinds need a cloud provider: attachments are refused outright when the
sidebar is pinned to a local model (``vision_available``), because the local
tier is not vision-capable and silently dropping an image would produce an
answer about a picture the model never saw.

Bytes live in the shared content-addressed store with note attachments, so the
same file attached twice is written once.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.chat import ChatAttachment
from backend.models.hierarchy import utcnow
from backend.paths import ATTACHMENTS_DIR
from backend.services.attachments import persist_bytes
from backend.services.providers.base import ImagePart
from backend.services.providers.waterfall import Waterfall

# Per-file ceiling. Lower than the 25 MB note-attachment cap: this file is
# converted or base64'd into a provider request, and a huge one buys a slow call
# and a blown context window rather than a better answer.
MAX_CHAT_ATTACHMENT_BYTES = 10 * 1024 * 1024

# Markdown extracted from one PDF, truncated to keep a 200-page upload from
# evicting the whole conversation from the prompt. Mirrors the retrieval cap:
# the sidebar answers questions, it does not ingest a textbook.
MAX_PDF_TEXT_CHARS = 20_000

IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
PDF_TYPES = {"application/pdf"}


class UnsupportedChatAttachmentError(ValueError):
    """The file isn't an accepted image/PDF type, is empty, or is too large."""


class AttachmentsUnavailableError(RuntimeError):
    """No vision-capable provider is available for this send."""


class PdfExtractionError(RuntimeError):
    """The PDF's text could not be extracted."""


def kind_for(content_type: str) -> str:
    """Map a content type to "image"/"pdf", or reject it."""
    content_type = (content_type or "").split(";", 1)[0].strip().lower()
    if content_type in IMAGE_TYPES:
        return "image"
    if content_type in PDF_TYPES:
        return "pdf"
    raise UnsupportedChatAttachmentError(content_type or "unknown type")


def vision_available(waterfall: Waterfall) -> bool:
    """True when some enabled provider in ``waterfall`` can accept images.

    Drives both the upload guard and the sidebar's "not available for this
    model" state, so the UI and the API agree on one rule.
    """
    return any(p.enabled and p.supports_vision for p in waterfall.providers)


def attachment_path(attachment: ChatAttachment) -> Path:
    """Where this attachment's bytes live: cache/attachments/<hash><ext>."""
    ext = Path(attachment.filename).suffix.lower()
    return ATTACHMENTS_DIR / f"{attachment.file_hash}{ext}"


def upload_attachment(
    session: Session,
    *,
    filename: str,
    content_type: str,
    data: bytes,
) -> ChatAttachment:
    """Validate and store one upload as a DRAFT attachment (no message yet).

    Committed with a NULL ``message_id``; ``chat.send_message`` links it to the
    turn it was sent with. PDF text is extracted here so the slow, CPU-bound
    conversion happens while the student is still typing rather than inside the
    send that also holds a provider call.
    """
    if not data:
        raise UnsupportedChatAttachmentError("empty file")
    if len(data) > MAX_CHAT_ATTACHMENT_BYTES:
        raise UnsupportedChatAttachmentError("file too large")
    kind = kind_for(content_type)

    file_hash = persist_bytes(data, filename)
    extracted = None
    if kind == "pdf":
        extracted = _reuse_or_extract_pdf_text(session, file_hash, filename)

    attachment = ChatAttachment(
        kind=kind,
        filename=filename,
        content_type=content_type,
        file_hash=file_hash,
        extracted_text=extracted,
    )
    session.add(attachment)
    session.commit()
    session.refresh(attachment)
    return attachment


def claim_drafts(session: Session, ids: list[int]) -> list[ChatAttachment]:
    """The draft attachments with these ids, in the order given.

    Only unlinked rows are returned: an id already attached to a turn is
    ignored, so replaying a send cannot steal another message's attachment or
    silently duplicate it.
    """
    if not ids:
        return []
    rows = session.execute(
        select(ChatAttachment)
        .where(ChatAttachment.id.in_(ids))
        .where(ChatAttachment.message_id.is_(None))
    ).scalars()
    by_id = {row.id: row for row in rows}
    return [by_id[i] for i in ids if i in by_id]


def discard_draft(session: Session, attachment_id: int) -> None:
    """Delete an unsent draft (the sidebar's "remove this chip")."""
    attachment = session.get(ChatAttachment, attachment_id)
    if attachment is None or attachment.message_id is not None:
        # Already sent, or never existed. Not an error: removing a chip is
        # idempotent from the UI's point of view.
        return
    file_hash, filename = attachment.file_hash, attachment.filename
    session.delete(attachment)
    session.commit()
    delete_orphaned_file(session, file_hash, filename)


def sweep_drafts(session: Session, *, older_than: timedelta) -> int:
    """Delete drafts never sent; returns how many went. Called by chat cleanup.

    A paste that was uploaded and then abandoned (tab closed, message never
    sent) would otherwise keep its row and its bytes forever.
    """
    cutoff = utcnow() - older_than
    stale = list(
        session.execute(
            select(ChatAttachment)
            .where(ChatAttachment.message_id.is_(None))
            .where(ChatAttachment.created_at < cutoff)
        ).scalars()
    )
    if not stale:
        return 0
    orphans = [(a.file_hash, a.filename) for a in stale]
    for attachment in stale:
        session.delete(attachment)
    session.commit()
    for file_hash, filename in orphans:
        delete_orphaned_file(session, file_hash, filename)
    return len(stale)


def image_parts(attachments: list[ChatAttachment]) -> list[ImagePart]:
    """The image attachments as provider image parts, skipping missing files.

    A file can go missing when the cache directory is cleared out from under a
    stored session; the conversation still opens and answers, just without that
    picture, which beats failing the whole send.
    """
    parts: list[ImagePart] = []
    for attachment in attachments:
        if attachment.kind != "image":
            continue
        path = attachment_path(attachment)
        if not path.is_file():
            continue
        parts.append(
            ImagePart(data=path.read_bytes(), mime_type=attachment.content_type)
        )
    return parts


def document_block(attachments: list[ChatAttachment]) -> str:
    """The PDF attachments' extracted text, framed for the prompt.

    Images are absent by design: they reach the model as image parts, so
    describing them here would be inventing content the model can already see.
    """
    pdfs = [a for a in attachments if a.kind == "pdf" and a.extracted_text]
    if not pdfs:
        return ""
    blocks = [
        f"## {a.filename}\n{a.extracted_text}" for a in pdfs
    ]
    body = "\n\n".join(blocks)
    return (
        "\n# Attached documents\n"
        "The student attached these files to the conversation. Ground your "
        "answer in them and say so plainly where they do not cover the "
        "question. A [...] marks text left out for length.\n\n"
        f"{body}\n"
    )


def delete_orphaned_file(session: Session, file_hash: str, filename: str) -> None:
    """Remove stored bytes once no chat or note attachment references them."""
    from backend.models import NoteAttachment  # local: avoids an import cycle

    still_used = session.scalar(
        select(func.count())
        .select_from(ChatAttachment)
        .where(ChatAttachment.file_hash == file_hash)
    ) or session.scalar(
        select(func.count())
        .select_from(NoteAttachment)
        .where(NoteAttachment.file_hash == file_hash)
    )
    if still_used:
        return
    path = ATTACHMENTS_DIR / f"{file_hash}{Path(filename).suffix.lower()}"
    if path.is_file():
        path.unlink()


# --- internals ---------------------------------------------------------------


def _reuse_or_extract_pdf_text(
    session: Session, file_hash: str, filename: str
) -> str:
    """Extracted markdown for this PDF, reusing a prior extraction if there is one.

    Storage is content-addressed, so the same PDF attached to a second
    conversation already has its markdown in another row — reuse it rather than
    paying markitdown again.
    """
    prior = session.execute(
        select(ChatAttachment.extracted_text)
        .where(ChatAttachment.file_hash == file_hash)
        .where(ChatAttachment.extracted_text.is_not(None))
        .limit(1)
    ).scalar_one_or_none()
    if prior:
        return prior

    path = ATTACHMENTS_DIR / f"{file_hash}{Path(filename).suffix.lower()}"
    try:
        # The ingestion pipeline's converter — one markitdown backend for the
        # whole app, so an attached PDF reads exactly like an uploaded one.
        from backend.services.pipeline.ingestion import _markitdown_convert

        text = _markitdown_convert(path)
    except Exception as exc:  # noqa: BLE001 - surfaced as a typed 4xx
        raise PdfExtractionError(str(exc)) from exc

    text = (text or "").strip()
    if not text:
        raise PdfExtractionError("no extractable text (is this a scanned PDF?)")
    if len(text) > MAX_PDF_TEXT_CHARS:
        text = text[:MAX_PDF_TEXT_CHARS].rstrip() + "\n\n[...]"
    return text
