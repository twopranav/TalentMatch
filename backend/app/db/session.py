"""
Postgres connection setup via SQLAlchemy.
Phase 2+ models import `Base`; routes depend on `get_db` for a request-scoped session.
"""
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    """FastAPI dependency — yields a DB session and guarantees it closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
