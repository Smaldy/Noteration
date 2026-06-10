"""add arcade resume_count (continue limit)

Revision ID: d1ace2b3c4d5
Revises: c0ffee1a2b3c
Create Date: 2026-06-10 19:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1ace2b3c4d5"
down_revision: str | None = "c0ffee1a2b3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing singleton rows default to 0 continues used.
    op.add_column(
        "arcade_state",
        sa.Column("resume_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("arcade_state", "resume_count")
