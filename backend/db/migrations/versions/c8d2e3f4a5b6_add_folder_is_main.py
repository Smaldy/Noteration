"""Add Folder.is_main — the subject's main folder.

Only the main folder auto-mirrors its subject's documents, so two folders
tagged to the same subject no longer both list every note in it.

Backfill: for each subject that already has tagged folders, the oldest one
becomes main. That preserves today's behavior for anyone with a single folder
per subject, and picks a deterministic winner for anyone with several.

Revision ID: c8d2e3f4a5b6
Revises: b7c1d2e3f4a5
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8d2e3f4a5b6"
down_revision = "b7c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "folders",
        sa.Column("is_main", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.execute(
        """
        UPDATE folders SET is_main = 1
        WHERE subject_id IS NOT NULL
          AND id IN (SELECT MIN(id) FROM folders
                     WHERE subject_id IS NOT NULL
                     GROUP BY subject_id)
        """
    )


def downgrade() -> None:
    op.drop_column("folders", "is_main")
