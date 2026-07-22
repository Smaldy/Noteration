"""Add chat_attachments — images and PDFs attached to an AI sidebar turn.

Images keep their bytes in the shared content-addressed store
(``cache/attachments/<hash>``) because a multimodal provider is re-sent the
picture on every turn. PDFs are converted to markdown once at upload and only
that text is kept in ``extracted_text``, so a long document costs its conversion
once instead of riding along as a file on each request.

``extracted_text`` is nullable precisely because the two kinds differ: it is the
markdown for a pdf row and NULL for an image row.

``message_id`` is nullable because an attachment is uploaded BEFORE the turn it
belongs to exists: pasting an image starts its upload (and, for a PDF, its text
extraction) while the student is still typing, so the send itself stays fast. A
row with a NULL message_id is a draft; ``chat.send_message`` links it to the
turn, and drafts nobody ever sent are swept by the chat cleanup pass.

Revision ID: fb3f3919ba91
Revises: d5e6f7a8b9c0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fb3f3919ba91"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chat_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "message_id",
            sa.Integer(),
            sa.ForeignKey("chat_messages.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("content_type", sa.String(), nullable=False),
        sa.Column("file_hash", sa.String(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    # Every read is "the attachments of this message", walked once per rendered
    # turn when a session is reopened.
    op.create_index(
        "ix_chat_attachments_message_id", "chat_attachments", ["message_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_chat_attachments_message_id", table_name="chat_attachments")
    op.drop_table("chat_attachments")
