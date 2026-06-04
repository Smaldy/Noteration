"""Per-subject queue lanes (Wave B): queue_jobs.subject_id + subjects.queue_state

Adds the denormalized lane key ``queue_jobs.subject_id`` (Topic→Chapter→Subject,
backfilled for existing rows, then enforced NOT NULL) so per-subject lane queries
don't re-join the hierarchy, and ``subjects.queue_state`` (running / paused /
overnight) — the per-subject lane state the user pauses/resumes. Existing rows:
subject_id backfilled from each job's topic; queue_state defaults to 'running'.

Revision ID: d9e0f1a2b3c4
Revises: c8d9e0f1a2b3
Create Date: 2026-06-04 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9e0f1a2b3c4"
down_revision: str | None = "c8d9e0f1a2b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add the column nullable + its FK (can't be NOT NULL until backfilled).
    with op.batch_alter_table("queue_jobs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("subject_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_queue_jobs_subject_id_subjects",
            "subjects",
            ["subject_id"],
            ["id"],
            ondelete="CASCADE",
        )
    # 2. Backfill each existing job's subject from its topic's chapter.
    op.execute(
        "UPDATE queue_jobs SET subject_id = ("
        " SELECT c.subject_id FROM topics t"
        " JOIN chapters c ON c.id = t.chapter_id"
        " WHERE t.id = queue_jobs.topic_id)"
    )
    # 3. Now every row has a value — enforce NOT NULL.
    with op.batch_alter_table("queue_jobs", schema=None) as batch_op:
        batch_op.alter_column(
            "subject_id", existing_type=sa.Integer(), nullable=False
        )
    # 4. Per-subject lane state.
    with op.batch_alter_table("subjects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "queue_state",
                sa.String(),
                nullable=False,
                server_default="running",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("subjects", schema=None) as batch_op:
        batch_op.drop_column("queue_state")
    with op.batch_alter_table("queue_jobs", schema=None) as batch_op:
        batch_op.drop_constraint("fk_queue_jobs_subject_id_subjects", type_="foreignkey")
        batch_op.drop_column("subject_id")
