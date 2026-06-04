"""history_events table (Wave C)

The append-only generation-history log (topic-generated events + provider
switches) that replaces overnight notifications. ``subject_id``/``topic_id`` are
nullable and ``SET NULL`` on delete so the log survives what it references.

Revision ID: 8624ad2393c6
Revises: d9e0f1a2b3c4
Create Date: 2026-06-04 14:03:05.080508
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import backend.db.types

# revision identifiers, used by Alembic.
revision: str = "8624ad2393c6"
down_revision: str | None = "d9e0f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "history_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Integer(), nullable=True),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum(
                "topic_generated",
                "provider_switch",
                name="historyeventtype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("provider_from", sa.String(), nullable=True),
        sa.Column("provider_to", sa.String(), nullable=True),
        sa.Column("detail", sa.String(), nullable=True),
        sa.Column("created_at", backend.db.types.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_id"],
            ["subjects.id"],
            name=op.f("fk_history_events_subject_id_subjects"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["topic_id"],
            ["topics.id"],
            name=op.f("fk_history_events_topic_id_topics"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_history_events")),
    )


def downgrade() -> None:
    op.drop_table("history_events")
