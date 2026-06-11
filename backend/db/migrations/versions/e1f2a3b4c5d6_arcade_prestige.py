"""add arcade prestige_count + active_special

Revision ID: e1f2a3b4c5d6
Revises: d1ace2b3c4d5
Create Date: 2026-06-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1f2a3b4c5d6"
down_revision: str | None = "d1ace2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing singleton rows start un-prestiged with no active special bullet.
    op.add_column(
        "arcade_state",
        sa.Column("prestige_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "arcade_state",
        sa.Column(
            "active_special", sa.String(), nullable=False, server_default="none"
        ),
    )


def downgrade() -> None:
    op.drop_column("arcade_state", "active_special")
    op.drop_column("arcade_state", "prestige_count")
