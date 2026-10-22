"""add interviewing to application_status

Revision ID: b8e5a3c1d702
Revises: 9fc843203d30
Create Date: 2026-10-22 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b8e5a3c1d702'
down_revision: Union[str, Sequence[str], None] = '9fc843203d30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ApplicationStatus.INTERVIEWING exists in the model, but no earlier
    # migration added it to the Postgres enum, and autogenerate cannot detect
    # a new enum value. ADD VALUE needs its own autocommitted block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE application_status ADD VALUE IF NOT EXISTS 'INTERVIEWING'")


def downgrade() -> None:
    """Downgrade schema."""
    # Postgres cannot remove a value from an enum type, so this is a no-op.
    pass
