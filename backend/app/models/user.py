import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, Boolean, Integer, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.job import Job

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
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), default=UserRole.USER, nullable=False
    )

    # --- profile fields, all roles ---
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # --- recruiter-specific ---
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- candidate-specific (role = USER); mirrors Job's matching fields ---
    skills: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    desired_role: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    jobs: Mapped[list["Job"]] = relationship(back_populates="created_by", cascade="all, delete-orphan")