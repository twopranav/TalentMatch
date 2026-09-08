"""
Auth primitives: password hashing + JWT create/verify.
This is the foundation Phase 2 (login/RBAC) will build on directly.
"""
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from jose import JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.hashers.bcrypt import BcryptHasher
from app.core.config import settings

# Modern password hashing context replacing passlib
pwd_context = PasswordHash((BcryptHasher(),))

def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """
    subject: typically the user id (as a string).
    extra_claims: e.g. {"role": "recruiter"} — used by Phase 2 RBAC checks.
    Every token gets a unique "jti" claim so a single token can be revoked
    (logout, forced session kill) without invalidating every other token
    the same user might have issued elsewhere.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode: dict[str, Any] = {"sub": subject, "exp": expire, "jti": str(uuid4())}
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Login throttling (brute-force protection)
# ---------------------------------------------------------------------------
# In-memory only — resets on process restart and is NOT shared across
# multiple app instances/workers. Good enough to stop naive password
# guessing right now; if you deploy with >1 worker or need this to survive
# restarts, move this to Redis (or a DB table with a migration) instead.
_LOGIN_ATTEMPT_LIMIT = 5
_LOGIN_LOCKOUT_MINUTES = 15
_failed_attempts: dict[str, list[datetime]] = {}
_locked_until: dict[str, datetime] = {}


def is_login_locked(email: str) -> tuple[bool, int]:
    """Returns (locked, seconds_remaining)."""
    until = _locked_until.get(email)
    if until is None:
        return False, 0
    now = datetime.now(timezone.utc)
    if now >= until:
        _locked_until.pop(email, None)
        _failed_attempts.pop(email, None)
        return False, 0
    return True, int((until - now).total_seconds())


def record_failed_login(email: str) -> None:
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=_LOGIN_LOCKOUT_MINUTES)
    attempts = [t for t in _failed_attempts.get(email, []) if t > window_start]
    attempts.append(now)
    _failed_attempts[email] = attempts
    if len(attempts) >= _LOGIN_ATTEMPT_LIMIT:
        _locked_until[email] = now + timedelta(minutes=_LOGIN_LOCKOUT_MINUTES)


def clear_failed_logins(email: str) -> None:
    _failed_attempts.pop(email, None)
    _locked_until.pop(email, None)