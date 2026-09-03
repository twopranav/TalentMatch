from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.core.security import decode_access_token
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
    user = db.get(User, user_id)
    if user is None:
        raise credentials_error
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