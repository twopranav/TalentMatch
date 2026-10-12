"""add shortlist stage and interview time to applications

Revision ID: 5b2d7c9e1a40
Revises: f3a9c1d2b7e8
Create Date: 2026-10-12

applications.shortlist_stage tracks where a shortlisted applicant is
(shortlisted / review / interview_scheduled / rejected); applications.interview_at
holds the interview date and time (timezone-aware) while the stage is
interview_scheduled. Existing shortlisted applications are backfilled to the
default stage.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5b2d7c9e1a40"
down_revision: Union[str, Sequence[str], None] = "f3a9c1d2b7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_stage = postgresql.ENUM(
    "SHORTLISTED", "REVIEW", "INTERVIEW_SCHEDULED", "REJECTED",
    name="shortlist_stage", create_type=False,
)


def upgrade() -> None:
    _stage.create(op.get_bind(), checkfirst=True)
    op.add_column("applications", sa.Column("shortlist_stage", _stage, nullable=True))
    op.add_column("applications", sa.Column("interview_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE applications SET shortlist_stage = 'SHORTLISTED' WHERE status = 'SHORTLISTED'")
    op.create_index("ix_applications_job_status", "applications", ["job_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_applications_job_status", table_name="applications")
    op.drop_column("applications", "interview_at")
    op.drop_column("applications", "shortlist_stage")
    _stage.drop(op.get_bind(), checkfirst=True)
