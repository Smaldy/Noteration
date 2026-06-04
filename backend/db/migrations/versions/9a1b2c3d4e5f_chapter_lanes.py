"""Chapter lanes (Chapter Lanes & Lazy Ingestion): chapters.queue_state +
chapters.page_start / page_end.

Adds a per-chapter lane (``queue_state``, reusing the running/paused/overnight
states) so processing can be focused on the chapters a student is actually
studying, and the outline-backed page range (``page_start`` / ``page_end``,
1-indexed inclusive, nullable) used for lazy per-chapter markdown extraction.

Existing chapters backfill to ``queue_state='paused'`` (server_default) and
``page_start=NULL`` / ``page_end=NULL`` (slide-deck / headingless behaviour
unchanged).

Revision ID: 9a1b2c3d4e5f
Revises: 8624ad2393c6
Create Date: 2026-06-04 13:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a1b2c3d4e5f"
down_revision: str | None = "8624ad2393c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "queue_state",
                sa.String(),
                nullable=False,
                server_default="paused",
            )
        )
        batch_op.add_column(sa.Column("page_start", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("page_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.drop_column("page_end")
        batch_op.drop_column("page_start")
        batch_op.drop_column("queue_state")
