"""add standalone skills extraction fields to resumes

Revision ID: 6d7734b43aa4
Revises: 4750ddc5ae8a
Create Date: 2026-09-22 11:58:47.743844

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6d7734b43aa4'
down_revision: Union[str, Sequence[str], None] = '4750ddc5ae8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('resumes', sa.Column('skills_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('resumes', sa.Column('skills_section_heading', sa.String(length=255), nullable=True))
    op.add_column(
        'resumes',
        sa.Column(
            'skills_extraction_status',
            sa.Enum('PENDING', 'PROCESSING', 'DONE', 'FAILED', name='resume_extraction_status', create_type=False),
            nullable=False,
            server_default='PENDING',
        ),
    )
    op.add_column('resumes', sa.Column('skills_extraction_error', sa.Text(), nullable=True))
    op.add_column('resumes', sa.Column('skills_extracted_at', sa.DateTime(), nullable=True))
    op.alter_column('resumes', 'skills_extraction_status', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('resumes', 'skills_extracted_at')
    op.drop_column('resumes', 'skills_extraction_error')
    op.drop_column('resumes', 'skills_extraction_status')
    op.drop_column('resumes', 'skills_section_heading')
    op.drop_column('resumes', 'skills_result')