import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class UserSession(Base):
    """One row per browser login. The access JWT carries this row's id in its
    "sid" claim, so revoking the row (logout, logout-all, refresh-token reuse)
    kills the access token on its very next use, not 15 minutes later.

    The refresh token itself is never stored, only its SHA-256. prev_refresh_hash
    remembers the token that was just replaced: presenting it again later means
    the old token leaked (or was replayed), and the whole session is revoked.
    """

    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_refresh_hash", "refresh_hash", unique=True),
        Index("ix_user_sessions_prev_refresh_hash", "prev_refresh_hash"),
        Index("ix_user_sessions_user_id", "user_id"),
        Index("ix_user_sessions_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    refresh_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prev_refresh_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Absolute end of the session (login time + SESSION_MAX_HOURS).
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(256), nullable=True)
