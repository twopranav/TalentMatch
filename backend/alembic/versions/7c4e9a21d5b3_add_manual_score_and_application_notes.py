"""add manual score and recruiter notes to applications

Revision ID: 7c4e9a21d5b3
Revises: 5b2d7c9e1a40
Create Date: 2026-10-12

applications.manual_score is a nullable, recruiter-entered 0-100 score kept
separate from the AI match_score (which is only ever written by the scoring
worker). application_notes holds recruiter notes: many per application,
append-only, deleted only along with their application.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7c4e9a21d5b3"
down_revision: Union[str, Sequence[str], None] = "5b2d7c9e1a40"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("manual_score", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_applications_manual_score_range",
        "applications",
        "manual_score IS NULL OR (manual_score >= 0 AND manual_score <= 100)",
    )

    op.create_table(
        "application_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("application_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("author_email", sa.String(length=255), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_application_notes_application", "application_notes", ["application_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_application_notes_application", table_name="application_notes")
    op.drop_table("application_notes")
    op.drop_constraint("ck_applications_manual_score_range", "applications", type_="check")
    op.drop_column("applications", "manual_score")
