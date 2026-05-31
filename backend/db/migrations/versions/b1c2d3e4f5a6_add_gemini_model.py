"""add settings.gemini_model

Revision ID: b1c2d3e4f5a6
Revises: da07b6080fba
Create Date: 2026-05-31 15:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "da07b6080fba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills the existing singleton row; the column is NOT NULL.
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "gemini_model",
                sa.String(),
                nullable=False,
                server_default="gemini-2.5-flash-lite",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("gemini_model")
