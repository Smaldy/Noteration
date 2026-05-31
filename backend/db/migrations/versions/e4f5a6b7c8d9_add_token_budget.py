"""add per-job token spend and per-document token budget

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-05-31 18:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Actual tokens a job spent (input+output), recorded on success — drives the
    # per-document soft cap and the queue view's spend display. Existing rows = 0.
    with op.batch_alter_table("queue_jobs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "tokens_used", sa.Integer(), nullable=False, server_default="0"
            )
        )
    # Per-document token ceiling. 0 = automatic (estimate × overspend factor);
    # a positive value is a flat ceiling. Existing rows default to 0 (auto).
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "per_document_token_budget",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("settings", schema=None) as batch_op:
        batch_op.drop_column("per_document_token_budget")
    with op.batch_alter_table("queue_jobs", schema=None) as batch_op:
        batch_op.drop_column("tokens_used")
