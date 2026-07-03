"""add settings.study_field + settings.ai_style

Revision ID: 9c67c9413583
Revises: a2b3c4d5e6f7
Create Date: 2026-07-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c67c9413583"
down_revision: str | None = "a2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills the existing singleton.
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "study_field",
                sa.String(),
                nullable=False,
                server_default="general",
            )
        )
        batch_op.add_column(
            sa.Column(
                "ai_style",
                sa.String(),
                nullable=False,
                server_default="balanced",
            )
        )
    # Pre-existing installs generated with a hardcoded "engineering tutor"
    # persona — keep their behavior unchanged; only fresh installs start at
    # the neutral "general".
    op.execute("UPDATE settings SET study_field = 'engineering'")


def downgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("ai_style")
        batch_op.drop_column("study_field")
