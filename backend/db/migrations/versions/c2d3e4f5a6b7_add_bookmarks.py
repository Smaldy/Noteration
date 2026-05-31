"""add bookmarked to subjects and topics

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-31 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "b1c2d3e4f5a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills existing rows to "not bookmarked"; NOT NULL.
    with op.batch_alter_table("subjects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "bookmarked", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )
    with op.batch_alter_table("topics", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "bookmarked", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("topics", schema=None) as batch_op:
        batch_op.drop_column("bookmarked")
    with op.batch_alter_table("subjects", schema=None) as batch_op:
        batch_op.drop_column("bookmarked")
