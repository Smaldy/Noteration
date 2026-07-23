"""Drop Subject.bookmarked.

Subject-level bookmarks are gone: the Library's bookmark filter now stars
*folders*, and notes are starred per folder on ``folder_items.bookmarked``.
Starring a subject had no surface left to act on.

Topic bookmarks (``topics.bookmarked``) are a different feature — the study
sidebar's per-topic stars — and are untouched.

Revision ID: e1f4a5b6c7d8
Revises: d9e3f4a5b6c7
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e1f4a5b6c7d8"
down_revision = "d9e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Batch mode: SQLite has no DROP COLUMN before 3.35, and Alembic's batch
    # rewrite is the portable way to express it.
    with op.batch_alter_table("subjects") as batch:
        batch.drop_column("bookmarked")


def downgrade() -> None:
    with op.batch_alter_table("subjects") as batch:
        batch.add_column(
            sa.Column("bookmarked", sa.Boolean(), nullable=False, server_default="0")
        )
