"""Add bookmarks to folders and to per-folder note placements.

The Library's bookmark filter now narrows folders rather than subjects, and a
note can be starred inside one folder without being starred everywhere.

Revision ID: d9e3f4a5b6c7
Revises: c8d2e3f4a5b6
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d9e3f4a5b6c7"
down_revision = "c8d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "folders",
        sa.Column("bookmarked", sa.Boolean(), nullable=False, server_default="0"),
    )
    op.add_column(
        "folder_items",
        sa.Column("bookmarked", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("folder_items", "bookmarked")
    op.drop_column("folders", "bookmarked")
