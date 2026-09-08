import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base


class TokenBlacklist(Base):
    """One row per revoked access token (by its jti claim). A row here means
    'this token must be rejected even though it hasn't expired yet' — that's
    the only thing a stateless JWT setup can't do on its own, which is what
    logout and forced-deactivation-of-an-active-session both need.

    expires_at mirrors the token's own `exp` claim so a cleanup job can
    safely delete rows once the token would have expired anyway — no point
    keeping a blacklist entry around for a token nobody could use again
    regardless."""

    __tablename__ = "token_blacklist"
    __table_args__ = (
        Index("ix_token_blacklist_expires_at", "expires_at"),
    )

    jti: Mapped[str] = mapped_column(String(36), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)