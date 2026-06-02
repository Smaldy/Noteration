"""add document mode (study | exam) for the Exam Prep section

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-02 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: str | None = "e4f5a6b7c8d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # How a document is processed/presented: 'study' = full pipeline (notes +
    # assessment), 'exam' = assessment-only (Exam Prep section). Existing rows
    # backfill to 'study' so current documents are unchanged.
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "mode",
                sa.String(),
                nullable=False,
                server_default="study",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_column("mode")
