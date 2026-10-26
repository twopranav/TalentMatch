"""Scheduled housekeeping for login state (Celery beat, see celery_app.py)."""
import logging

from app.core.celery_app import celery_app
from app.core.sessions import purge_expired_sessions
from app.core.token_blacklist import purge_expired_blacklist_entries
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(name="auth_cleanup.purge")
def purge_auth_rows() -> None:
    """Delete sessions and revoked-token rows that can never matter again, so
    the two tables don't grow forever."""
    db = SessionLocal()
    try:
        sessions = purge_expired_sessions(db)
        tokens = purge_expired_blacklist_entries(db)
        if sessions or tokens:
            logger.info("Auth cleanup: removed %d session(s), %d blacklisted token(s).", sessions, tokens)
    finally:
        db.close()
