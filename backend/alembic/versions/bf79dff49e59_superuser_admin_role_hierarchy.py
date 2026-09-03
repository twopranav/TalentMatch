"""superuser admin role hierarchy

Revision ID: bf79dff49e59
Revises: 925e0c6fdb88
Create Date: 2026-09-03 12:02:29.908697

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bf79dff49e59'
down_revision: Union[str, Sequence[str], None] = '925e0c6fdb88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # renaming/adding enum values can't run inside the same transaction
    # as other DDL — same constraint as the original RBAC migration
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role RENAME VALUE 'ADMIN' TO 'SUPERUSER'")
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'ADMIN'")

    # the "only one" constraint follows the renamed role, not the label —
    # drop the old index, create the new one under a name that matches
    op.execute("DROP INDEX IF EXISTS one_admin_only")
    op.execute("CREATE UNIQUE INDEX one_superuser_only ON users (role) WHERE role = 'SUPERUSER'")

    # new self-registrations (always RECRUITER/USER — nothing lets a
    # registration request ADMIN/SUPERUSER) now default to inactive,
    # pending admin approval
    op.execute("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT false")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TABLE users ALTER COLUMN is_active SET DEFAULT true")

    op.execute("DROP INDEX IF EXISTS one_superuser_only")
    op.execute("CREATE UNIQUE INDEX one_admin_only ON users (role) WHERE role = 'SUPERUSER'")

    # NOTE: this downgrade is one-way-lossy if any row has been set to the
    # new 'ADMIN' value — Postgres can't remove an enum value, and renaming
    # SUPERUSER back to ADMIN would collide with rows already using 'ADMIN'.
    # Safe only if no ADMIN-role rows exist at downgrade time.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role RENAME VALUE 'SUPERUSER' TO 'ADMIN'")