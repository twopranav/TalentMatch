"""add llm_configs table

Revision ID: a1b2c3d4e5f6
Revises: 6d292f70d295
Create Date: 2026-09-23 00:00:00.000000

Backs the no-code "change model" admin page: one row per extraction
task (resume_skills, jd_skills), holding the active provider+model.

Seeded with provider="unset" / model="unset" placeholders, not a real
model -- no default provider has been chosen yet. Both extraction tasks
will raise UnknownProviderError (app/core/llm_client.py) until an admin
sets a real provider+model for each task via:

    PUT /api/admin/llm-config/resume_skills
    PUT /api/admin/llm-config/jd_skills

/health/llm reports which tasks are still unset.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "6d292f70d295"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLACEHOLDER = "unset"


def upgrade() -> None:
    op.create_table(
        "llm_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("task", sa.String(length=50), nullable=False, unique=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    llm_configs = sa.table(
        "llm_configs",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("task", sa.String),
        sa.column("provider", sa.String),
        sa.column("model", sa.String),
    )
    op.bulk_insert(
        llm_configs,
        [
            {"id": uuid.uuid4(), "task": "resume_skills", "provider": _PLACEHOLDER, "model": _PLACEHOLDER},
            {"id": uuid.uuid4(), "task": "jd_skills", "provider": _PLACEHOLDER, "model": _PLACEHOLDER},
        ],
    )


def downgrade() -> None:
    op.drop_table("llm_configs")
