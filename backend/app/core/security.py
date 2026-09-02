"""
Auth primitives: password hashing + JWT create/verify.
This is the foundation Phase 2 (login/RBAC) will build on directly.
"""
from datetime import datetime, timedelta, timezone
from typing import Any
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
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode: dict[str, Any] = {"sub": subject, "exp": expire}
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None