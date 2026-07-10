"""add todo_items

Revision ID: a1b2c3d4e5f6
Revises: b906bf108836
Create Date: 2026-07-10 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "b906bf108836"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The to-do list: one row per pinned topic. The checked state is derived
    # from topics.studied, so nothing beyond the reference is stored here.
    op.create_table(
        "todo_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("topic_id"),
    )


def downgrade() -> None:
    op.drop_table("todo_items")
