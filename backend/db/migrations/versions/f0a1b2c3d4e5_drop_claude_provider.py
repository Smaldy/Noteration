"""drop the Claude provider's settings columns

Revision ID: f0a1b2c3d4e5
Revises: c9d0e1f2a3b4
Create Date: 2026-07-12 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f0a1b2c3d4e5"
down_revision: str | None = "c9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The paid Claude tier is gone (providers/claude.py removed), taking its
    # stored key and the allow_paid gate with it. batch_alter_table keeps the
    # drop safe on older SQLite builds.
    with op.batch_alter_table("settings") as batch:
        batch.drop_column("api_key_claude")
        batch.drop_column("allow_paid")


def downgrade() -> None:
    with op.batch_alter_table("settings") as batch:
        batch.add_column(sa.Column("api_key_claude", sa.String(), nullable=True))
        batch.add_column(
            sa.Column(
                "allow_paid",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
