"""add topics.pdf_pages (per-topic PDF page list for exact source slicing)

Revision ID: a2b3c4d5e6f7
Revises: e1f2a3b4c5d6
Create Date: 2026-07-02 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a2b3c4d5e6f7"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable JSON list of 1-indexed pages; existing topics keep None (they
    # slice their source by heading / proportional order, as before).
    with op.batch_alter_table("topics", schema=None) as batch_op:
        batch_op.add_column(sa.Column("pdf_pages", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("topics", schema=None) as batch_op:
        batch_op.drop_column("pdf_pages")
