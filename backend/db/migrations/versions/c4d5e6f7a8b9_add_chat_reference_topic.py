"""add the assistant's reference topic to chat sessions

Revision ID: c4d5e6f7a8b9
Revises: f1a2b3c4d5e6
Create Date: 2026-07-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The sidebar's reference-topic chip, pinned per session. SET NULL: deleting
    # a topic unpins the chip and leaves the conversation intact.
    with op.batch_alter_table("chat_sessions") as batch:
        batch.add_column(sa.Column("topic_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_chat_sessions_topic_id",
            "topics",
            ["topic_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("chat_sessions") as batch:
        batch.drop_constraint("fk_chat_sessions_topic_id", type_="foreignkey")
        batch.drop_column("topic_id")
