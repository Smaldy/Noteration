"""add settings.font_family_heading

Revision ID: b906bf108836
Revises: 9c67c9413583
Create Date: 2026-07-03 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b906bf108836"
down_revision: str | None = "9c67c9413583"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NULL = keep the built-in display face (Montserrat), mirroring how a NULL
    # font_family means the built-in body face.
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("font_family_heading", sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("font_family_heading")
