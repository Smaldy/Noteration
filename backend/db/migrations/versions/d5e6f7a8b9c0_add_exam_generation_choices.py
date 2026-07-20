"""Add per-document exam generation choices (question types + writing style).

Exam Prep uploads now pick which assessment types to generate and, optionally, a
writing style that overrides the global ``Settings.ai_style``. Both live on the
document so a later regeneration reproduces the same deck.

``question_types`` is NOT NULL with a ``both`` server default, which is exactly
the behaviour every existing document already had. ``ai_style`` is nullable and
backfills as NULL, meaning "follow the global setting" — so existing documents
keep tracking Settings as before.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.add_column(
            sa.Column(
                "question_types",
                sa.String(),
                nullable=False,
                server_default="both",
            )
        )
        batch.add_column(sa.Column("ai_style", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_column("ai_style")
        batch.drop_column("question_types")
