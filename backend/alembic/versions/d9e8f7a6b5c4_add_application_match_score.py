"""add application match score

Revision ID: d9e8f7a6b5c4
Revises: c7d8e9f0a1b2
Create Date: 2026-09-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d9e8f7a6b5c4"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("match_score", sa.Float(), nullable=True))
    op.add_column(
        "applications",
        sa.Column("match_status", sa.String(16), server_default="pending", nullable=False),
    )
    op.add_column("applications", sa.Column("match_details", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("applications", sa.Column("match_error", sa.Text(), nullable=True))
    op.add_column("applications", sa.Column("matched_at", sa.DateTime(), nullable=True))
    op.create_index("ix_applications_job_score", "applications", ["job_id", "match_score"])


def downgrade() -> None:
    op.drop_index("ix_applications_job_score", table_name="applications")
    op.drop_column("applications", "matched_at")
    op.drop_column("applications", "match_error")
    op.drop_column("applications", "match_details")
    op.drop_column("applications", "match_status")
    op.drop_column("applications", "match_score")
