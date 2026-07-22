"""add chat_sessions.closed_at

Marks a conversation the assistant ended itself after sustained abuse. Nullable
and defaulting to NULL, so every existing session stays open.

Revision ID: aed22c9912fe
Revises: fb3f3919ba91
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "aed22c9912fe"
down_revision = "fb3f3919ba91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions", sa.Column("closed_at", sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("chat_sessions", "closed_at")
