"""add the ollama_always_model manual pin

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-11 18:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # When set, this model serves every local call and overrides the
    # fast/quality role split (services/local_ai/runtime.py).
    op.add_column(
        "settings", sa.Column("ollama_always_model", sa.String(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("settings", "ollama_always_model")
