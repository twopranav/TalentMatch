"""
DB-backed token revocation. Kept separate from core/security.py (which stays
pure JWT/hashing logic with no DB dependency) so security.py can still be
unit-tested without a database.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models.token_blacklist import TokenBlacklist


def blacklist_token(db: Session, jti: str, expires_at: datetime) -> None:
    # merge, not add: logging out twice with the same still-valid token
    # (e.g. a retried request) should not raise a duplicate-PK error.
    db.merge(TokenBlacklist(jti=jti, expires_at=expires_at))
    db.commit()


def is_token_blacklisted(db: Session, jti: str) -> bool:
    return db.get(TokenBlacklist, jti) is not None


def purge_expired_blacklist_entries(db: Session) -> int:
    """Delete blacklist rows for tokens that would have expired naturally by
    now anyway — safe to run on a schedule (cron/scheduled task) to keep the
    table from growing forever. Returns the number of rows deleted."""
    deleted = (
        db.query(TokenBlacklist)
        .filter(TokenBlacklist.expires_at < datetime.now(timezone.utc))
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted