import uuid
from datetime import datetime
from enum import Enum as PyEnum
from sqlalchemy import String, Enum as SAEnum, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.session import Base
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.job import Job

class UserRole(str, PyEnum):
    """Plain Python enum — reused both as the Postgres column type below
    and as the value you'll put in the JWT's extra_claims in security.py."""
    RECRUITER = "recruiter"
    ADMIN = "admin"
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
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    jobs: Mapped[list["Job"]] = relationship(back_populates="created_by", cascade="all, delete-orphan")