"""add arcade minigame tables

Revision ID: c0ffee1a2b3c
Revises: 2295db6ff51b
Create Date: 2026-06-08 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c0ffee1a2b3c"
down_revision: str | None = "2295db6ff51b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "arcade_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("coins", sa.Integer(), nullable=False),
        sa.Column("score_balance", sa.Integer(), nullable=False),
        sa.Column("high_score", sa.Integer(), nullable=False),
        sa.Column("wave_record", sa.Integer(), nullable=False),
        sa.Column("resumable_wave", sa.Integer(), nullable=False),
        sa.Column("resumable_score", sa.Integer(), nullable=False),
        sa.Column("daily_mcq_count", sa.Integer(), nullable=False),
        sa.Column("daily_quest_date", sa.Date(), nullable=True),
        sa.Column("daily_bonus_claimed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arcade_state")),
    )
    op.create_table(
        "arcade_upgrades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arcade_upgrades")),
        sa.UniqueConstraint("key", name=op.f("uq_arcade_upgrades_key")),
    )
    op.create_table(
        "arcade_play_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ended_at", sa.DateTime(), nullable=True),
        sa.Column("start_wave", sa.Integer(), nullable=False),
        sa.Column("wave_reached", sa.Integer(), nullable=False),
        sa.Column("score_earned", sa.Integer(), nullable=False),
        sa.Column("died", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_arcade_play_sessions")),
    )


def downgrade() -> None:
    op.drop_table("arcade_play_sessions")
    op.drop_table("arcade_upgrades")
    op.drop_table("arcade_state")
