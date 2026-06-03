"""schedule_entries.is_deadline (exam/deadline markers)

A deadline/exam marker on the calendar, kept in sync with ``Subject.exam_date``.
Existing rows default to not-a-deadline.

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-06-03 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a6b7c8d9e0f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("schedule_entries", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_deadline", sa.Boolean(), nullable=False, server_default="0"
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("schedule_entries", schema=None) as batch_op:
        batch_op.drop_column("is_deadline")
