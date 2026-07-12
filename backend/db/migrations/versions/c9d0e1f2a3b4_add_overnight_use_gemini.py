"""add overnight_use_gemini setting

Revision ID: c9d0e1f2a3b4
Revises: e5f6a7b8c9d0
Create Date: 2026-07-11 20:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Route overnight batch generation through Gemini rather than the local
    # quality model (services/local_ai/runtime.py, services/worker.py).
    op.add_column(
        "settings",
        sa.Column(
            "overnight_use_gemini",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "overnight_use_gemini")
