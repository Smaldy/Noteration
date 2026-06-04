"""Calendar hourly scheduling: schedule_entries.start_time + day-view settings

Adds an optional ``start_time`` (time-of-day) to a calendar entry so a session can
be pinned to an hour in the new hourly Day view, plus three Settings columns that
configure that view: the visible hour window [start, end) and the slot gap in
minutes. Existing rows: no start_time (all-day), defaults 8:00–23:00 / 60-min slots.

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-06-04 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("schedule_entries", schema=None) as batch_op:
        batch_op.add_column(sa.Column("start_time", sa.Time(), nullable=True))
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "calendar_day_start_hour",
                sa.Integer(),
                nullable=False,
                server_default="8",
            )
        )
        batch_op.add_column(
            sa.Column(
                "calendar_day_end_hour",
                sa.Integer(),
                nullable=False,
                server_default="23",
            )
        )
        batch_op.add_column(
            sa.Column(
                "calendar_slot_minutes",
                sa.Integer(),
                nullable=False,
                server_default="60",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("calendar_slot_minutes")
        batch_op.drop_column("calendar_day_end_hour")
        batch_op.drop_column("calendar_day_start_hour")
    with op.batch_alter_table("schedule_entries", schema=None) as batch_op:
        batch_op.drop_column("start_time")
