import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, Boolean, Integer, Enum as SAEnum, func, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.job import Job
    from app.models.application import Application

class UserRole(str, PyEnum):
    """SUPERUSER: exactly one- enforced by a DB unique partial index.
    ADMIN: many allowed, promoted/demoted only by the superuser.
    RECRUITER / USER: unchanged."""
    SUPERUSER = "superuser"
    ADMIN = "admin"
    RECRUITER = "recruiter"
    USER = "user"

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Mirrors a DB-level partial unique index created directly in
        # bf79dff49e59_superuser_admin_role_hierarchy.py (not via this
        # model originally). Declaring it here stops `alembic revision
        # --autogenerate` from seeing it as unmanaged drift and proposing
        # to drop it on every future migration.
        Index(
            "one_superuser_only",
            "role",
            unique=True,
            postgresql_where=text("role = 'SUPERUSER'::user_role"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), default=UserRole.USER, nullable=False
    )

    # Set at signup when someone asks to be a recruiter. Stays populated
    # until an admin approves (-> promotes `role` to RECRUITER and clears
    # this) or explicitly rejects it (-> cleared, recruiter_rejected_at set).
    # NEVER read this column for permission checks — only `role` grants
    # access. This column only means "there's a pending request."
    requested_role: Mapped[UserRole | None] = mapped_column(
        SAEnum(UserRole, name="user_role"), nullable=True, default=None
    )
    # Set only by the explicit reject action below. Lets you tell "never
    # asked to be a recruiter" apart from "asked, and was turned down" —
    # both look identical (requested_role=None, role=USER) without this.
    recruiter_rejected_at: Mapped[datetime | None] = mapped_column(nullable=True, default=None)

    # --- profile fields, all roles ---
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # --- recruiter-specific ---
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- candidate-specific (role = USER); mirrors Job's matching fields ---
    skills: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    desired_role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_blob_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    applications: Mapped[list["Application"]] = relationship(back_populates="user", cascade="all, delete-orphan")   
    jobs: Mapped[list["Job"]] = relationship(back_populates="created_by", cascade="all, delete-orphan")