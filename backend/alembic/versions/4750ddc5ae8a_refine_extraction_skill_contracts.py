"""refine extraction skill contracts

Revision ID: 4750ddc5ae8a
Revises: bf95d0d002e2
Create Date: 2026-09-15 17:49:37.113454
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "4750ddc5ae8a"
down_revision: Union[str, Sequence[str], None] = "bf95d0d002e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "jobs",
        "extracted_required_skills",
        new_column_name="extracted_compulsory_skills",
    )

    op.add_column(
        "jobs",
        sa.Column(
            "extracted_skills",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )

    op.add_column(
        "resumes",
        sa.Column(
            "extracted_stated_experience",
            sa.Text(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column(
        "resumes",
        "extracted_stated_experience",
    )

    op.drop_column(
        "jobs",
        "extracted_skills",
    )

    op.alter_column(
        "jobs",
        "extracted_compulsory_skills",
        new_column_name="extracted_required_skills",
    )