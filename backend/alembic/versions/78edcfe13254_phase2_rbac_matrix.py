"""phase2 rbac matrix

Revision ID: 78edcfe13254
Revises: b4f00e4a8bfa
Create Date: 2026-09-02 16:06:40.784027

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '78edcfe13254'
down_revision: Union[str, Sequence[str], None] = 'b4f00e4a8bfa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Adding a value to a Postgres enum type can't run inside the same
    # transaction as other DDL — must be its own autocommitted block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'USER'")

    op.add_column("jobs", sa.Column("jd_raw_text", sa.Text(), nullable=True))

    # DB-level backstop: at most one ADMIN row can ever exist, enforced by
    # Postgres itself regardless of application-code bugs.
    op.execute("CREATE UNIQUE INDEX one_admin_only ON users (role) WHERE role = 'ADMIN'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS one_admin_only")
    op.drop_column("jobs", "jd_raw_text")
    # Postgres can't remove a value from an enum type once added — the
    # USER role addition is effectively one-way; a true downgrade would
    # require recreating the enum type from scratch.