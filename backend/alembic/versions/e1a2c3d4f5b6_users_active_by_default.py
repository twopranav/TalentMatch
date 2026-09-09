"""users active by default

Revision ID: e1a2c3d4f5b6
Revises: 7081755dc02d
Create Date: 2026-09-09 14:56:20.000000

Approval now only gates promotion to RECRUITER (via requested_role), not
login. bf79dff49e59 previously flipped this default to false to force
every new signup through admin approval before they could log in at all;
this reverts that so signups are active immediately, matching the ORM-level
default in app/models/user.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1a2c3d4f5b6'
down_revision: Union[str, Sequence[str], None] = '7081755dc02d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT true")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT false")