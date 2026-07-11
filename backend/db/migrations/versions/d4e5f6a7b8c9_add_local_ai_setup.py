"""add local AI setup table and two-model settings fields

Revision ID: d4e5f6a7b8c9
Revises: a1b2c3d4e5f6
Create Date: 2026-07-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Two-model local AI: fast = interactive default, quality = overnight
    # (and interactive when prefer_quality is on). The legacy ollama_model
    # column stays as the manual-override slot.
    op.add_column("settings", sa.Column("ollama_fast_model", sa.String(), nullable=True))
    op.add_column(
        "settings", sa.Column("ollama_quality_model", sa.String(), nullable=True)
    )
    op.add_column(
        "settings",
        sa.Column(
            "ollama_prefer_quality",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    # Singleton state row for the detect → confirm → install flow; resumable
    # across restarts (see models/local_ai.py).
    op.create_table(
        "local_ai_setup",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("hardware", sa.JSON(), nullable=True),
        sa.Column("selection", sa.JSON(), nullable=True),
        sa.Column("chosen", sa.JSON(), nullable=True),
        sa.Column("quality_model", sa.String(), nullable=True),
        sa.Column("fast_model", sa.String(), nullable=True),
        sa.Column("pull_tag", sa.String(), nullable=True),
        sa.Column("pull_completed", sa.Integer(), nullable=False),
        sa.Column("pull_total", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("local_ai_setup")
    op.drop_column("settings", "ollama_prefer_quality")
    op.drop_column("settings", "ollama_quality_model")
    op.drop_column("settings", "ollama_fast_model")
