"""
Shared fixtures for the whole test suite.

Tests run against a SEPARATE Postgres database (your DATABASE_URL + "_test"),
never your dev DB. Real Alembic migrations are applied to it once per test
session — not Base.metadata.create_all() — because the RBAC migration adds
an enum value and a partial unique index via raw SQL that only exist in the
migration file, not in the SQLAlchemy models, so create_all() would miss them.
"""
import io
import os
import subprocess
import sys
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core import security as security_module
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
    fail on the second admin-related test in a run). Truncates every table
    the app writes to, not just jobs/users — token_blacklist and audit_logs
    are written as side effects of auth/CRUD flows, and resumes/applications
    both reference users/jobs by FK, so they all need to go together."""
    yield
    with test_engine.connect() as conn:
        conn.execute(text(
            "TRUNCATE token_blacklist, audit_logs, applications, resumes, jobs, users "
            "RESTART IDENTITY CASCADE"
        ))
        conn.commit()


@pytest.fixture(autouse=True)
def _reset_login_throttle():
    """core/security.py's login-lockout state (_failed_attempts,
    _locked_until) lives in module-level dicts, not the DB — _clean_tables
    never touches it. Without this, a lockout triggered by one test (e.g.
    5 failed logins) would still be in effect for the next test that
    happens to reuse the same email, and tests that assert lockout
    behavior would leak into each other."""
    yield
    security_module._failed_attempts.clear()
    security_module._locked_until.clear()


@pytest.fixture(autouse=True)
def _isolated_storage_root(tmp_path, monkeypatch):
    """Redirects local-disk blob storage (resumes + avatars both go through
    app.core.storage.local_disk, which reads settings.LOCAL_STORAGE_ROOT at
    call time) to a per-test temp dir, so uploaded-file tests never read or
    write the real ./storage/resumes directory or leak files across tests."""
    monkeypatch.setattr(settings, "LOCAL_STORAGE_ROOT", str(tmp_path / "storage"))

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
    """
    make_user(role=UserRole.RECRUITER) -> (User, raw_password)
    make_user(requested_role=UserRole.RECRUITER) -> a plain USER with a
    pending recruiter request, for testing the approval/rejection flow.
    is_active defaults to True for every role, matching the real app's
    current default (self-registration is active immediately — see
    models/user.py's default and test_register_is_active_immediately) —
    pass is_active=False explicitly to simulate a deactivated account.
    """
    def _make(
        role: UserRole = UserRole.USER,
        email: str | None = None,
        requested_role: UserRole | None = None,
        is_active: bool | None = None,
    ):
        if is_active is None:
            is_active = True
        email = email or f"{role.value}-{uuid.uuid4().hex[:8]}@test.com"
        password = "testpass123"
        user = User(
            email=email,
            hashed_password=hash_password(password),
            role=role,
            requested_role=requested_role,
            is_active=is_active,
        )
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


@pytest.fixture()
def pdf_bytes():
    """pdf_bytes("some text") -> real, parseable minimal PDF bytes (built
    with reportlab), not fake bytes wearing a .pdf extension — this matters
    for any test that exercises actual content-parsing, not just the
    upload/validation path."""
    def _make(text: str = "Sample content") -> bytes:
        from reportlab.pdfgen import canvas
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(100, 750, text)
        c.save()
        return buf.getvalue()
    return _make


@pytest.fixture()
def docx_bytes():
    """docx_bytes("some text") -> real, parseable minimal DOCX bytes (built
    with python-docx)."""
    def _make(text: str = "Sample content") -> bytes:
        from docx import Document
        buf = io.BytesIO()
        doc = Document()
        doc.add_paragraph(text)
        doc.save(buf)
        return buf.getvalue()
    return _make