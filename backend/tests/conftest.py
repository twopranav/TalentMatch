"""
Shared fixtures for the whole test suite.

Tests run against a SEPARATE Postgres database (your DATABASE_URL + "_test"),
never your dev DB. Real Alembic migrations are applied to it once per test
session — not Base.metadata.create_all() — because the RBAC migration adds
an enum value and a partial unique index via raw SQL that only exist in the
migration file, not in the SQLAlchemy models, so create_all() would miss them.
"""
import os
import subprocess
import sys
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models.user import User, UserRole

BACKEND_DIR = Path(__file__).resolve().parent.parent

def _test_db_url(url: str) -> str:
    base, _, dbname = url.rpartition("/")
    return f"{base}/{dbname}_test"

TEST_DATABASE_URL = _test_db_url(settings.DATABASE_URL)
test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    """Runs once for the whole test run: creates the test DB if it doesn't
    exist yet, then applies real migrations to it via `alembic upgrade head`."""
    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    dbname = TEST_DATABASE_URL.rsplit("/", 1)[1]
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": dbname}
        ).first()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    admin_engine.dispose()
    env = os.environ.copy()
    env["DATABASE_URL"] = TEST_DATABASE_URL
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
    )

@pytest.fixture(autouse=True)
def _clean_tables():
    """Runs after every test — wipes all rows so tests never affect each
    other (important here since 'only one admin can exist' would otherwise
    fail on the second admin-related test in a run)."""
    yield
    with test_engine.connect() as conn:
        conn.execute(text("TRUNCATE jobs, users RESTART IDENTITY CASCADE"))
        conn.commit()

def _override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = _override_get_db

@pytest.fixture()
def db():
    """A DB session tests can use directly for setup, separate from the
    one the API itself uses per-request."""
    session = TestSessionLocal()
    yield session
    session.close()

@pytest.fixture()
def client():
    return TestClient(app)

@pytest.fixture()
def make_user(db):
    """make_user(role=UserRole.RECRUITER) -> (User, raw_password)"""
    def _make(role: UserRole = UserRole.USER, email: str | None = None):
        email = email or f"{role.value}-{uuid.uuid4().hex[:8]}@test.com"
        password = "testpass123"
        user = User(email=email, hashed_password=hash_password(password), role=role)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user, password
    return _make

@pytest.fixture()
def auth_headers():
    """auth_headers(user) -> {"Authorization": "Bearer <token>"}"""
    def _headers(user: User) -> dict:
        token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.value})
        return {"Authorization": f"Bearer {token}"}
    return _headers