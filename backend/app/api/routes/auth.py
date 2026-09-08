from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.audit import record_audit, snapshot
from app.core.deps import get_current_user, oauth2_scheme
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    is_login_locked,
    record_failed_login,
    clear_failed_logins,
)
from app.core.token_blacklist import blacklist_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserRead, Token, ChangePassword

router = APIRouter()

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Signup never writes role=RECRUITER directly, no matter what was asked
    # for. If they asked for RECRUITER, that request is only *recorded* in
    # requested_role — the account is a plain, functional USER (role stays
    # at the model default) until an admin approves it via PATCH .../active.
    requested_role = payload.role if payload.role == UserRole.RECRUITER else None

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        requested_role=requested_role,
    )
    db.add(user)
    db.flush()  # assigns user.id before we snapshot it for the audit row
    record_audit(
        db, actor=None, action="create", resource_type="user",
        resource_id=user.id, after=snapshot(user, "user"),
    )
    db.commit()
    db.refresh(user)  # pulls back server-generated fields: id (default=uuid4 fired here), created_at
    return user

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Token:
    email = form_data.username
    # OAuth2PasswordRequestForm always calls the field "username" — we're
    # treating email as the username, which is why form_data.username is the email.

    locked, seconds_remaining = is_login_locked(email)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Try again in {seconds_remaining // 60 + 1} minute(s).",
        )

    user = db.query(User).filter(User.email == email).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        record_failed_login(email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    clear_failed_logins(email)

    if not user.is_active:
        # New signups start is_active=False and stay that way until an
        # admin approves them (or approves+promotes a recruiter request).
        # Without this check they could log in and use the app immediately,
        # which defeats the whole approval workflow in users.py.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is inactive or pending admin approval.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.value})
    return Token(access_token=token)

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # also confirms the token is currently valid
):
    """Revoke the current access token immediately, rather than leaving it
    usable until it naturally expires. Tokens issued before this feature
    shipped have no jti and can't be individually revoked this way — they
    just expire on schedule, same as before."""
    payload = decode_access_token(token)
    jti = payload.get("jti") if payload else None
    if jti is None:
        return  # nothing to blacklist; client should still discard the token locally
    exp_ts = payload.get("exp")
    expires_at = (
        datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        if exp_ts is not None
        else datetime.now(timezone.utc) + timedelta(minutes=5)
    )
    blacklist_token(db, jti, expires_at)

@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Self-service password change while logged in. Not a substitute for a
    'forgot password' flow — that needs an email provider (SMTP/SendGrid/etc.)
    which isn't wired up yet, so it's intentionally out of scope here."""
    if not verify_password(payload.current_password, current_user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.hashed_password = hash_password(payload.new_password)
    # hashed_password is excluded from snapshot() (see _SNAPSHOT_EXCLUDE), so
    # before/after would be identical and uninformative — record the event
    # itself instead of a no-op diff.
    record_audit(
        db, actor=current_user, action="update", resource_type="user",
        resource_id=current_user.id,
        before={"password_changed": False}, after={"password_changed": True},
    )
    db.commit()