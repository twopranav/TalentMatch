from datetime import datetime, timedelta, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core import sessions as session_store
from app.core.audit import record_audit, snapshot
from app.core.auth_cookies import (
    clear_auth_cookies,
    new_csrf_if_missing,
    set_access_cookie,
    set_csrf_cookie,
    set_refresh_cookie,
    verify_csrf,
)
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.rate_limit import limit_by_ip
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
from app.models.user_session import UserSession
from app.schemas.user import UserCreate, UserRead, Token, ChangePassword

router = APIRouter()

@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(limit_by_ip("register", 10, 3600))],
)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    # Signup never writes role=RECRUITER or ADMIN directly, no matter what was
    # asked for. A request for either is only *recorded* in requested_role,
    # together with the sub company they picked — the account is a plain,
    # functional USER (role stays at the model default) until the superuser
    # approves it via POST /users/{id}/approve-request.
    requested_role = payload.role if payload.role in (UserRole.RECRUITER, UserRole.ADMIN) else None

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        requested_role=requested_role,
        sub_company=payload.sub_company if requested_role else None,
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

@router.post(
    "/login",
    response_model=Token,
    dependencies=[Depends(limit_by_ip("login", 20, 60))],
)
def login(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
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
        # Accounts deactivated by an admin or the superuser land here; the
        # same check runs on every request in core/deps.py.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is inactive. Contact your administrator.",
        )

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    # Start a browser session: one DB row + the three cookies. The access token
    # is also returned in the body so scripts and tests can keep using
    # `Authorization: Bearer`; the web app ignores it and relies on the cookies.
    session_row, refresh_raw = session_store.create_session(
        db,
        user.id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role.value, "sid": str(session_row.id)},
    )
    set_access_cookie(response, token)
    set_refresh_cookie(response, refresh_raw)
    set_csrf_cookie(response, session_store.new_csrf_token())
    return Token(access_token=token)


def _unauthorized_clearing_cookies(detail: str) -> JSONResponse:
    resp = JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": detail})
    clear_auth_cookies(resp)
    return resp


@router.post(
    "/refresh",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(limit_by_ip("refresh", 120, 60))],
)
def refresh(request: Request, db: Session = Depends(get_db)):
    """Silent renewal: trade the refresh cookie for a new access cookie and a
    rotated refresh cookie. Called by the frontend when an API call returns 401."""
    verify_csrf(request)
    raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not raw:
        return _unauthorized_clearing_cookies("No active session")

    row, presented_previous = session_store.find_by_refresh_token(db, raw)
    if row is None:
        return _unauthorized_clearing_cookies("Session not found")

    now = datetime.now(timezone.utc)
    if not session_store.is_live(row, now) or session_store.is_idle_expired(row, now):
        session_store.revoke(db, row)
        return _unauthorized_clearing_cookies("Session expired")

    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        session_store.revoke(db, row)
        return _unauthorized_clearing_cookies("Account is inactive")

    new_refresh: str | None = None
    if presented_previous:
        # An already-rotated token. Two tabs refreshing at once do this
        # legitimately, so a short grace window after rotation is allowed (and
        # only a new access token is issued; the winner's refresh cookie
        # stays). Anything later is a replay: kill the whole session.
        if not session_store.within_grace(row, now):
            session_store.revoke(db, row)
            return _unauthorized_clearing_cookies("Session revoked")
        row.last_used_at = now
        db.commit()
    else:
        new_refresh = session_store.rotate(db, row)

    access = create_access_token(
        subject=str(user.id), extra_claims={"role": user.role.value, "sid": str(row.id)}
    )
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_access_cookie(resp, access)
    if new_refresh is not None:
        set_refresh_cookie(resp, new_refresh)
    set_csrf_cookie(resp, new_csrf_if_missing(request))
    return resp

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: Session = Depends(get_db)):
    """End this browser session. Works with the Bearer token (scripts/tests)
    and with the cookies (web app). The refresh cookie alone is enough, so a
    user whose 15-minute access token already lapsed can still log out for real
    instead of being silently logged back in by the next refresh.
    Needs *some* valid credential, otherwise 401."""
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    token = token or request.cookies.get(settings.ACCESS_COOKIE_NAME)
    payload = decode_access_token(token) if token else None

    session_row: UserSession | None = None
    sid = payload.get("sid") if payload else None
    if sid:
        try:
            session_row = db.get(UserSession, uuid.UUID(str(sid)))
        except (ValueError, TypeError):
            session_row = None
    if session_row is None:
        raw = request.cookies.get(settings.REFRESH_COOKIE_NAME)
        if raw:
            session_row, _ = session_store.find_by_refresh_token(db, raw)

    if payload is None and session_row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload is not None and payload.get("jti"):
        exp_ts = payload.get("exp")
        expires_at = (
            datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            if exp_ts is not None
            else datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        blacklist_token(db, payload["jti"], expires_at)
    if session_row is not None:
        session_store.revoke(db, session_row)

    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(resp)
    return resp


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sign this account out of every browser/device at once."""
    session_store.revoke_all_for_user(db, current_user.id)
    resp = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_auth_cookies(resp)
    return resp

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