import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.security import decode_access_token
from app.core.token_blacklist import is_token_blacklisted
from app.db.session import get_db
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_error
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_error
    # Tokens issued before this feature shipped have no "jti" and simply
    # can't be checked — they fall through and stay valid until they expire
    # naturally, same as before. Every token issued from now on has one.
    jti = payload.get("jti")
    if jti is not None and is_token_blacklisted(db, jti):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This session has been logged out. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        # A malformed or tampered token can carry a "sub" that isn't a
        # valid UUID at all. Without this, db.get() raises a raw DB/driver
        # error that FastAPI turns into an unhandled 500 instead of a
        # clean 401 — this normalizes it back into "invalid credentials".
        user_uuid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise credentials_error
    user = db.get(User, user_uuid)
    if user is None:
        raise credentials_error
    if not user.is_active:
        # Re-checked on every request (not just at login) because JWTs are
        # stateless: an admin deactivating this user via PATCH .../active
        # must take effect on their very next call, not wait for their
        # existing token to expire.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account is inactive or pending approval.",
        )
    return user

def require_role(*allowed_roles: UserRole):
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action")
        return current_user
    return checker

# SUPERUSER is included everywhere ADMIN is, since the superuser is a strict
# superset of admin power — "god" role, can do anything an admin can plus
# the admin-promotion/demotion actions only it can do.
require_recruiter_or_admin = require_role(UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPERUSER)
require_admin_or_superuser = require_role(UserRole.ADMIN, UserRole.SUPERUSER)
require_superuser = require_role(UserRole.SUPERUSER)
require_any_authenticated = get_current_user