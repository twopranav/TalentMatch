"""
Browser sessions: one `user_sessions` row per login, a rotating opaque refresh
token, and the rules for when a session is still alive.

Pure DB logic with no HTTP in it (cookies live in auth_cookies.py), so it can be
unit-tested directly.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user_session import UserSession


def _now() -> datetime:
    return datetime.now(timezone.utc)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def create_session(
    db: Session, user_id: uuid.UUID, ip: str | None, user_agent: str | None
) -> tuple[UserSession, str]:
    """Start a session. Returns (row, raw refresh token). The raw token exists
    only here and in the cookie; the database keeps its hash."""
    raw = new_refresh_token()
    now = _now()
    row = UserSession(
        user_id=user_id,
        refresh_hash=hash_token(raw),
        created_at=now,
        last_used_at=now,
        expires_at=now + timedelta(hours=settings.SESSION_MAX_HOURS),
        ip=(ip or None) and ip[:64],
        user_agent=(user_agent or None) and user_agent[:256],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, raw


def is_live(row: UserSession, now: datetime | None = None) -> bool:
    """Not revoked and inside the absolute lifetime (the idle limit is a
    separate check, done at refresh time)."""
    now = now or _now()
    return row.revoked_at is None and now < row.expires_at


def is_idle_expired(row: UserSession, now: datetime | None = None) -> bool:
    now = now or _now()
    return now > row.last_used_at + timedelta(minutes=settings.SESSION_IDLE_MINUTES)


def revoke(db: Session, row: UserSession) -> None:
    if row.revoked_at is None:
        row.revoked_at = _now()
        db.commit()


def revoke_all_for_user(db: Session, user_id: uuid.UUID, except_id: uuid.UUID | None = None) -> int:
    q = db.query(UserSession).filter(
        UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
    )
    if except_id is not None:
        q = q.filter(UserSession.id != except_id)
    n = q.update({UserSession.revoked_at: _now()}, synchronize_session=False)
    db.commit()
    return n


def find_by_refresh_token(db: Session, raw: str) -> tuple[UserSession | None, bool]:
    """(session, presented_a_previous_token). A token that matches the current
    hash is the normal case; one that matches only prev_refresh_hash was already
    rotated away and is either a harmless race between two tabs or a replay."""
    h = hash_token(raw)
    row = db.query(UserSession).filter(UserSession.refresh_hash == h).first()
    if row is not None:
        return row, False
    row = db.query(UserSession).filter(UserSession.prev_refresh_hash == h).first()
    return row, row is not None


def rotate(db: Session, row: UserSession) -> str:
    """Swap in a new refresh token and remember the old one. Returns the raw
    new token."""
    raw = new_refresh_token()
    now = _now()
    row.prev_refresh_hash = row.refresh_hash
    row.refresh_hash = hash_token(raw)
    row.rotated_at = now
    row.last_used_at = now
    db.commit()
    return raw


def within_grace(row: UserSession, now: datetime | None = None) -> bool:
    now = now or _now()
    return row.rotated_at is not None and now - row.rotated_at <= timedelta(
        seconds=settings.SESSION_REFRESH_GRACE_SECONDS
    )


def purge_expired_sessions(db: Session) -> int:
    """Delete sessions that can never be used again (past their absolute
    lifetime, or revoked more than a day ago). Safe to run on a schedule."""
    now = _now()
    n = (
        db.query(UserSession)
        .filter(
            (UserSession.expires_at < now)
            | (UserSession.revoked_at.is_not(None) & (UserSession.revoked_at < now - timedelta(days=1)))
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return n
