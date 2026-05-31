"""add order_index to documents

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-05-31 17:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing rows default to 0; the list query tie-breaks on uploaded_at desc,
    # so current ordering is preserved until the user drags cards to reorder.
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "order_index", sa.Integer(), nullable=False, server_default="0"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_column("order_index")
