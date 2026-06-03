"""calendar manual + custom events on schedule_entries

Make ``topic_id`` nullable (custom/subject events have no topic) and add
``subject_id`` (FK, for whole-subject + AI-plan sessions), ``title``,
``description``, ``completed``, and ``completed_at``. Existing SM-2 rows keep
their topic and default to not-completed.

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-06-03 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6b7c8d9e0f1"
down_revision: str | None = "f5a6b7c8d9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("schedule_entries", schema=None) as batch_op:
        batch_op.alter_column("topic_id", existing_type=sa.Integer(), nullable=True)
        batch_op.add_column(
            sa.Column("subject_id", sa.Integer(), nullable=True)
        )
        batch_op.add_column(sa.Column("title", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("description", sa.String(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "completed", sa.Boolean(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(sa.Column("completed_at", sa.Date(), nullable=True))
        batch_op.create_foreign_key(
            "fk_schedule_entries_subject_id_subjects",
            "subjects",
            ["subject_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("schedule_entries", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_schedule_entries_subject_id_subjects", type_="foreignkey"
        )
        batch_op.drop_column("completed_at")
        batch_op.drop_column("completed")
        batch_op.drop_column("description")
        batch_op.drop_column("title")
        batch_op.drop_column("subject_id")
        batch_op.alter_column("topic_id", existing_type=sa.Integer(), nullable=False)
