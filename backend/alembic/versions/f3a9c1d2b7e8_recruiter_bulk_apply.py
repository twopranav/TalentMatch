"""recruiter bulk apply: applications without a candidate account

Revision ID: f3a9c1d2b7e8
Revises: a2edbdc2c703
Create Date: 2026-10-08

applications.user_id becomes nullable (NULL = a recruiter applied a
bulk-uploaded resume on behalf of a candidate with no account),
applications.submitted_by_id records who did it, and a partial unique
index stops the same resume being applied to the same job twice in that
case (uq_application_user_job can't, since NULLs never collide).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a9c1d2b7e8"
down_revision: Union[str, Sequence[str], None] = "a2edbdc2c703"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("applications", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.add_column(
        "applications",
        sa.Column("submitted_by_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_applications_submitted_by_id_users",
        "applications", "users", ["submitted_by_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(
        "uq_application_job_resume_unowned",
        "applications",
        ["job_id", "resume_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_application_job_resume_unowned", table_name="applications")
    op.drop_constraint("fk_applications_submitted_by_id_users", "applications", type_="foreignkey")
    op.drop_column("applications", "submitted_by_id")
    # NOT NULL can't be restored while recruiter-submitted rows exist, and
    # they have no user to attach to, so they are dropped.
    op.execute("DELETE FROM applications WHERE user_id IS NULL")
    op.alter_column("applications", "user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
