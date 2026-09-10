"""add phase 4 extraction fields to resumes and jobs

Revision ID: bf95d0d002e2
Revises: e1a2c3d4f5b6
Create Date: 2026-09-10 16:16:00.816602

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'bf95d0d002e2'
down_revision: Union[str, Sequence[str], None] = 'e1a2c3d4f5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()

    # --- ENUM types must exist before any ADD COLUMN references them.
    # Autogenerate emits the Enum inline on add_column, which works for a
    # brand-new table (CREATE TABLE creates the type as a side effect) but
    # NOT for ALTER TABLE ADD COLUMN against an existing table — hence
    # "type ... does not exist". checkfirst=True makes this safe to rerun.
    resume_extraction_status = postgresql.ENUM(
        'PENDING', 'PROCESSING', 'DONE', 'FAILED', name='resume_extraction_status'
    )
    resume_extraction_status.create(bind, checkfirst=True)

    job_extraction_status = postgresql.ENUM(
        'PENDING', 'PROCESSING', 'DONE', 'FAILED', name='job_extraction_status'
    )
    job_extraction_status.create(bind, checkfirst=True)

    # --- resumes ---
    op.add_column('resumes', sa.Column('raw_text', sa.Text(), nullable=True))
    # server_default required: existing rows need a value for this NOT
    # NULL column at ALTER-TABLE time (the Python-level default on the ORM
    # model only applies to rows inserted after this point). Dropped again
    # below once the column is populated everywhere.
    op.add_column(
        'resumes',
        sa.Column(
            'extraction_status',
            resume_extraction_status,
            nullable=False,
            server_default='PENDING',
        ),
    )
    op.add_column('resumes', sa.Column('extraction_error', sa.Text(), nullable=True))
    op.add_column('resumes', sa.Column('extracted_at', sa.DateTime(), nullable=True))
    op.add_column('resumes', sa.Column('extracted_skills', postgresql.JSONB(), nullable=True))
    op.add_column('resumes', sa.Column('extracted_experience_years', sa.Integer(), nullable=True))
    op.add_column('resumes', sa.Column('extracted_education', postgresql.JSONB(), nullable=True))
    op.add_column('resumes', sa.Column('extracted_certifications', postgresql.JSONB(), nullable=True))
    op.add_column('resumes', sa.Column('extracted_profile', postgresql.JSONB(), nullable=True))
    op.alter_column('resumes', 'extraction_status', server_default=None)

    # --- jobs ---
    op.add_column(
        'jobs',
        sa.Column(
            'extraction_status',
            job_extraction_status,
            nullable=False,
            server_default='PENDING',
        ),
    )
    op.add_column('jobs', sa.Column('extraction_error', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('extracted_at', sa.DateTime(), nullable=True))
    op.add_column('jobs', sa.Column('extracted_required_skills', postgresql.JSONB(), nullable=True))
    op.add_column('jobs', sa.Column('extracted_min_experience_years', sa.Integer(), nullable=True))
    op.add_column('jobs', sa.Column('extracted_max_experience_years', sa.Integer(), nullable=True))
    op.add_column('jobs', sa.Column('extracted_education_requirement', sa.String(length=255), nullable=True))
    op.add_column('jobs', sa.Column('extracted_profile', postgresql.JSONB(), nullable=True))
    op.alter_column('jobs', 'extraction_status', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('jobs', 'extracted_profile')
    op.drop_column('jobs', 'extracted_education_requirement')
    op.drop_column('jobs', 'extracted_max_experience_years')
    op.drop_column('jobs', 'extracted_min_experience_years')
    op.drop_column('jobs', 'extracted_required_skills')
    op.drop_column('jobs', 'extracted_at')
    op.drop_column('jobs', 'extraction_error')
    op.drop_column('jobs', 'extraction_status')

    op.drop_column('resumes', 'extracted_profile')
    op.drop_column('resumes', 'extracted_certifications')
    op.drop_column('resumes', 'extracted_education')
    op.drop_column('resumes', 'extracted_experience_years')
    op.drop_column('resumes', 'extracted_skills')
    op.drop_column('resumes', 'extracted_at')
    op.drop_column('resumes', 'extraction_error')
    op.drop_column('resumes', 'extraction_status')
    op.drop_column('resumes', 'raw_text')

    bind = op.get_bind()
    postgresql.ENUM(name='job_extraction_status').drop(bind, checkfirst=True)
    postgresql.ENUM(name='resume_extraction_status').drop(bind, checkfirst=True)