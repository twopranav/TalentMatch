"""Setting, clearing and verifying the login cookies (see config.py for the model)."""
import hmac

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_HEADER = "x-csrf-token"

_ACCESS_PATH = "/api"
_REFRESH_PATH = "/api/auth"
_CSRF_PATH = "/"


def _samesite() -> str:
    return settings.COOKIE_SAMESITE.lower()


def set_access_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.ACCESS_COOKIE_NAME,
        token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path=_ACCESS_PATH,
        httponly=True,
        secure=settings.COOKIES_SECURE,
        samesite=_samesite(),
    )


def set_refresh_cookie(response: Response, token: str) -> None:
    # No max_age: a session cookie, so closing the browser ends the login.
    # Strict + a path of /api/auth: it is only ever sent to the auth endpoints,
    # and never on a request that starts from another site.
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        token,
        path=_REFRESH_PATH,
        httponly=True,
        secure=settings.COOKIES_SECURE,
        samesite="strict",
    )


def set_csrf_cookie(response: Response, token: str) -> None:
    # Readable by the page on purpose (double-submit): the frontend copies it
    # into the X-CSRF-Token header. Its presence also tells the frontend that a
    # login exists, so it knows to try /users/me or a silent refresh.
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        token,
        path=_CSRF_PATH,
        httponly=False,
        secure=settings.COOKIES_SECURE,
        samesite=_samesite(),
    )


def new_csrf_if_missing(request: Request) -> str:
    """Keep the browser's existing CSRF token across a refresh (so other open
    tabs stay valid); mint one only if the cookie is somehow gone."""
    existing = request.cookies.get(settings.CSRF_COOKIE_NAME)
    if existing:
        return existing
    import secrets
    return secrets.token_urlsafe(32)


def clear_auth_cookies(response: Response) -> None:
    for name, path in (
        (settings.ACCESS_COOKIE_NAME, _ACCESS_PATH),
        (settings.REFRESH_COOKIE_NAME, _REFRESH_PATH),
        (settings.CSRF_COOKIE_NAME, _CSRF_PATH),
    ):
        response.delete_cookie(name, path=path)


def verify_csrf(request: Request) -> None:
    """Double-submit check: the X-CSRF-Token header must equal the tm_csrf cookie.
    A page on another site can make the browser send our cookies but cannot read
    the cookie to copy it into a header."""
    cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not hmac.compare_digest(cookie, header):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid")
