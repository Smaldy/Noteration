"""add documents.source_type and documents.status_detail (audio transcriber)

Revision ID: b9c0d1e2f3a4
Revises: f6a7b8c9d0e1
Create Date: 2026-06-05 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b9c0d1e2f3a4"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default 'pdf' backfills every existing document as a PDF (NOT NULL);
    # status_detail is nullable (nothing to say by default). The DocumentStatus enum
    # gained ``transcribing``, so widen the (non-native) status VARCHAR to fit it.
    new_status = sa.Enum(
        "transcribing",
        "uploaded",
        "processing",
        "ready",
        "error",
        name="documentstatus",
        native_enum=False,
    )
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_type",
                sa.String(),
                nullable=False,
                server_default="pdf",
            )
        )
        batch_op.add_column(
            sa.Column("status_detail", sa.String(), nullable=True),
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=10),
            type_=new_status,
            existing_nullable=False,
        )


def downgrade() -> None:
    old_status = sa.Enum(
        "uploaded",
        "processing",
        "ready",
        "error",
        name="documentstatus",
        native_enum=False,
    )
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=12),
            type_=old_status,
            existing_nullable=False,
        )
        batch_op.drop_column("status_detail")
        batch_op.drop_column("source_type")
