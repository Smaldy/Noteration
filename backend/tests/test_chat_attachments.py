"""Chat attachments — upload, draft claiming, and how each kind reaches the model."""

from __future__ import annotations

import base64

import pytest
from sqlalchemy.orm import Session

import backend.models  # noqa: F401 - register models on Base.metadata
from backend.models.chat import ChatAttachment
from backend.services import chat as chatsvc
from backend.services import chat_attachments as ca
from backend.services.providers.mock import MockProvider
from backend.services.providers.waterfall import Waterfall

# Smallest valid PNG (1x1). Real bytes matter: the upload path hashes them and
# writes them to the content-addressed store.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
def vision() -> MockProvider:
    return MockProvider("gemini_free", text="ok", supports_vision=True)


@pytest.fixture
def local() -> MockProvider:
    return MockProvider("ollama", text="ok", supports_vision=False)


def _use(monkeypatch: pytest.MonkeyPatch, *providers: MockProvider) -> None:
    monkeypatch.setattr(chatsvc, "_build_waterfall", lambda _s: Waterfall(list(providers)))


def _upload(session: Session, name: str = "paste.png") -> ChatAttachment:
    return ca.upload_attachment(
        session, filename=name, content_type="image/png", data=_PNG
    )


def test_vision_availability_follows_the_configured_providers(
    vision: MockProvider, local: MockProvider
) -> None:
    assert ca.vision_available(Waterfall([vision])) is True
    assert ca.vision_available(Waterfall([local])) is False
    # One cloud provider alongside a local one is still enough.
    assert ca.vision_available(Waterfall([local, vision])) is True


def test_upload_creates_an_unlinked_draft(session: Session) -> None:
    attachment = _upload(session)
    assert attachment.kind == "image"
    # NULL message_id is what makes it a draft: uploaded, not yet sent.
    assert attachment.message_id is None
    assert ca.attachment_path(attachment).is_file()


def test_send_links_the_draft_and_passes_the_image_to_the_provider(
    session: Session, vision: MockProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, vision)
    attachment = _upload(session)

    chatsvc.send_message(session, message="what is this?", attachment_ids=[attachment.id])

    session.refresh(attachment)
    assert attachment.message_id is not None  # no longer a draft
    assert vision.last_images is not None and len(vision.last_images) == 1
    # The real mime travels with the bytes rather than being guessed provider-side.
    assert vision.last_images[0].mime_type == "image/png"
    assert vision.last_images[0].data == _PNG
    # The turn names its files so a multi-image thread stays attributable.
    assert "[attached: paste.png]" in (vision.last_prompt or "")


def test_a_sent_draft_cannot_be_claimed_again(
    session: Session, vision: MockProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards a retried send from stealing another turn's attachment."""
    _use(monkeypatch, vision)
    attachment = _upload(session)
    chatsvc.send_message(session, message="first", attachment_ids=[attachment.id])

    assert ca.claim_drafts(session, [attachment.id]) == []


def test_attachments_are_refused_when_only_a_local_model_is_configured(
    session: Session, local: MockProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The local tier can't see an image, so the send is refused, not degraded."""
    _use(monkeypatch, local)
    attachment = _upload(session)

    with pytest.raises(ca.AttachmentsUnavailableError):
        chatsvc.send_message(session, message="hi", attachment_ids=[attachment.id])

    # The picture was never silently dropped into a text-only call.
    assert local.last_images is None


def test_a_plain_send_still_works_with_a_local_model(
    session: Session, local: MockProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only attachments need vision — ordinary chat must not regress."""
    _use(monkeypatch, local)
    _, reply = chatsvc.send_message(session, message="hi")
    assert reply.content == "ok"


@pytest.mark.parametrize("content_type", ["text/plain", "video/mp4", ""])
def test_unsupported_types_are_rejected(session: Session, content_type: str) -> None:
    with pytest.raises(ca.UnsupportedChatAttachmentError):
        ca.upload_attachment(
            session, filename="x", content_type=content_type, data=b"data"
        )


def test_oversized_and_empty_uploads_are_rejected(session: Session) -> None:
    with pytest.raises(ca.UnsupportedChatAttachmentError):
        ca.upload_attachment(
            session, filename="e.png", content_type="image/png", data=b""
        )
    with pytest.raises(ca.UnsupportedChatAttachmentError):
        ca.upload_attachment(
            session,
            filename="big.png",
            content_type="image/png",
            data=b"x" * (ca.MAX_CHAT_ATTACHMENT_BYTES + 1),
        )


def test_discarding_a_draft_removes_row_and_bytes(session: Session) -> None:
    attachment = _upload(session)
    path = ca.attachment_path(attachment)

    ca.discard_draft(session, attachment.id)

    assert session.get(ChatAttachment, attachment.id) is None
    assert not path.is_file()


def test_discarding_a_sent_attachment_is_a_no_op(
    session: Session, vision: MockProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only drafts are discardable; a sent turn keeps its attachment."""
    _use(monkeypatch, vision)
    attachment = _upload(session)
    chatsvc.send_message(session, message="q", attachment_ids=[attachment.id])

    ca.discard_draft(session, attachment.id)

    assert session.get(ChatAttachment, attachment.id) is not None


def test_sweep_reclaims_only_stale_drafts(
    session: Session, vision: MockProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import timedelta

    from backend.models.hierarchy import utcnow

    _use(monkeypatch, vision)
    fresh = _upload(session, "fresh.png")
    stale = _upload(session, "stale.png")
    sent = _upload(session, "sent.png")
    chatsvc.send_message(session, message="q", attachment_ids=[sent.id])
    stale.created_at = utcnow() - timedelta(hours=48)
    session.commit()

    swept = ca.sweep_drafts(session, older_than=timedelta(hours=6))

    assert swept == 1
    assert session.get(ChatAttachment, stale.id) is None
    assert session.get(ChatAttachment, fresh.id) is not None
    assert session.get(ChatAttachment, sent.id) is not None


def test_pdf_text_grounds_the_prompt_while_images_do_not(session: Session) -> None:
    """PDFs ride in as text; images must NOT be described in the prompt."""
    pdf = ChatAttachment(
        kind="pdf",
        filename="notes.pdf",
        content_type="application/pdf",
        file_hash="h1",
        extracted_text="Ohm's law states V = IR.",
    )
    image = ChatAttachment(
        kind="image", filename="p.png", content_type="image/png", file_hash="h2"
    )

    block = ca.document_block([pdf, image])

    assert "Ohm's law states V = IR." in block
    assert "notes.pdf" in block
    # The model sees the picture itself; narrating it here would invent content.
    assert "p.png" not in block
    assert ca.document_block([image]) == ""
