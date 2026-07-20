"""add settings.chat_retention (assistant history retention)

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-07-14 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "e7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "chat_retention",
            sa.String(),
            nullable=False,
            server_default="keep_last_5",
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table("settings") as batch:
        batch.drop_column("chat_retention")
