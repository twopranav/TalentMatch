"""add sub_company to users and jobs

Revision ID: 9fc843203d30
Revises: 7c4e9a21d5b3
Create Date: 2026-10-22 05:59:58.386719

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9fc843203d30'
down_revision: Union[str, Sequence[str], None] = '7c4e9a21d5b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('applications', sa.Column('interview_stage', sa.Enum('SCHEDULED', 'REJECTED', 'HIRED', name='interview_stage', native_enum=False, length=16), nullable=True))
    op.add_column('jobs', sa.Column('sub_company', sa.Enum('PHOTOVOLTAIC', 'SOLAR', 'TECHNOLOGIES', name='sub_company', native_enum=False, length=32), nullable=True))
    op.create_index(op.f('ix_jobs_sub_company'), 'jobs', ['sub_company'], unique=False)
    op.add_column('users', sa.Column('sub_company', sa.Enum('PHOTOVOLTAIC', 'SOLAR', 'TECHNOLOGIES', name='sub_company', native_enum=False, length=32), nullable=True))
    op.create_index(op.f('ix_users_sub_company'), 'users', ['sub_company'], unique=False)

    # Backfill. The superuser keeps NULL on purpose.
    op.execute(
        "UPDATE users SET sub_company = 'TECHNOLOGIES' "
        "WHERE sub_company IS NULL "
        "AND (role IN ('ADMIN', 'RECRUITER') OR requested_role IS NOT NULL)"
    )
    op.execute(
        "UPDATE jobs SET sub_company = u.sub_company "
        "FROM users u WHERE jobs.created_by_id = u.id AND jobs.sub_company IS NULL "
        "AND u.sub_company IS NOT NULL"
    )
    op.execute("UPDATE jobs SET sub_company = 'TECHNOLOGIES' WHERE sub_company IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_users_sub_company'), table_name='users')
    op.drop_column('users', 'sub_company')
    op.drop_index(op.f('ix_jobs_sub_company'), table_name='jobs')
    op.drop_column('jobs', 'sub_company')
    op.drop_column('applications', 'interview_stage')