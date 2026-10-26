"""
Cookie sessions: login sets httpOnly cookies, the access cookie authenticates
(with CSRF protection on writes), refresh rotates the refresh token, and a
session ends on logout, idle timeout, absolute timeout, replay of a rotated
token, or deactivation.

Bearer-token behaviour (scripts, other tests) is covered in test_auth.py.
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core import sessions as session_store
from app.core.config import Settings, settings
from app.main import app
from app.models.user import User, UserRole
from app.models.user_session import UserSession

LOGIN = "/api/auth/login"
REFRESH = "/api/auth/refresh"
LOGOUT = "/api/auth/logout"
LOGOUT_ALL = "/api/auth/logout-all"
ME = "/api/users/me"


@pytest.fixture(autouse=True)
def _plain_http_cookies(monkeypatch):
    # The test client talks http://, which would drop Secure cookies.
    monkeypatch.setattr(settings, "COOKIE_SECURE", False)


def _login(client, user, password):
    resp = client.post(LOGIN, data={"username": user.email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp


def _set_cookie(resp, name):
    """Raw value of a cookie set by this response, or None."""
    for header in resp.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header.split(";", 1)[0].split("=", 1)[1]
    return None


def _set_cookie_header(resp, name):
    return next((h for h in resp.headers.get_list("set-cookie") if h.startswith(f"{name}=")), None)


def _csrf(client):
    return {"X-CSRF-Token": client.cookies.get("tm_csrf")}


def _refresh_with(client, refresh_token, csrf):
    """POST /refresh presenting exactly these cookies (an explicit Cookie header
    bypasses the client's cookie jar)."""
    return client.post(
        REFRESH,
        headers={"Cookie": f"tm_refresh={refresh_token}; tm_csrf={csrf}", "X-CSRF-Token": csrf},
    )


@pytest.fixture()
def logged_in(client, make_user):
    user, password = make_user(role=UserRole.RECRUITER)
    resp = _login(client, user, password)
    return user, password, resp


# ------------------------------------------------------------------ login

def test_login_sets_the_three_cookies_with_the_right_flags(logged_in):
    _, _, resp = logged_in
    access = _set_cookie_header(resp, "tm_access")
    refresh = _set_cookie_header(resp, "tm_refresh")
    csrf = _set_cookie_header(resp, "tm_csrf")
    assert access and refresh and csrf

    assert "httponly" in access.lower() and "path=/api" in access.lower()
    assert "httponly" in refresh.lower() and "path=/api/auth" in refresh.lower()
    assert "samesite=strict" in refresh.lower()
    # the refresh token is a session cookie: no Max-Age / Expires
    assert "max-age" not in refresh.lower() and "expires" not in refresh.lower()
    # the page must be able to read the CSRF cookie
    assert "httponly" not in csrf.lower()


def test_login_marks_cookies_secure_when_configured(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "COOKIE_SECURE", True)
    user, password = make_user()
    resp = client.post(LOGIN, data={"username": user.email, "password": password})
    for name in ("tm_access", "tm_refresh", "tm_csrf"):
        assert "secure" in _set_cookie_header(resp, name).lower()


def test_login_creates_a_session_row_and_tags_the_token(logged_in, db):
    user, _, resp = logged_in
    rows = db.query(UserSession).filter(UserSession.user_id == user.id).all()
    assert len(rows) == 1
    assert rows[0].revoked_at is None
    # only the hash of the refresh token is stored
    raw = _set_cookie(resp, "tm_refresh")
    assert rows[0].refresh_hash == session_store.hash_token(raw) != raw


# --------------------------------------------------------- cookie authentication

def test_cookie_authenticates_without_a_bearer_header(client, logged_in):
    assert client.get(ME).status_code == 200


def test_no_cookie_and_no_bearer_is_401(client):
    assert client.get(ME).status_code == 401


def test_cookie_write_without_csrf_header_is_rejected(client, logged_in):
    assert client.post(LOGOUT_ALL).status_code == 403
    # still logged in: the rejected request did nothing
    assert client.get(ME).status_code == 200


def test_cookie_write_with_csrf_header_is_accepted(client, logged_in):
    assert client.post(LOGOUT_ALL, headers=_csrf(client)).status_code == 204


def test_cookie_write_with_a_wrong_csrf_header_is_rejected(client, logged_in):
    assert client.post(LOGOUT_ALL, headers={"X-CSRF-Token": "not-the-token"}).status_code == 403


def test_bearer_requests_need_no_csrf_header(client, logged_in):
    token = logged_in[2].json()["access_token"]
    fresh = TestClient(app)  # no cookies at all
    assert fresh.post(LOGOUT_ALL, headers={"Authorization": f"Bearer {token}"}).status_code == 204


# ---------------------------------------------------------------- refresh

def test_refresh_requires_the_csrf_header(client, logged_in):
    assert client.post(REFRESH).status_code == 403


def test_refresh_without_a_refresh_cookie_is_401(client):
    resp = client.post(REFRESH, headers={"Cookie": "tm_csrf=abc", "X-CSRF-Token": "abc"})
    assert resp.status_code == 401


def test_refresh_rotates_the_refresh_token_and_keeps_the_session_alive(client, logged_in, db):
    old_refresh = _set_cookie(logged_in[2], "tm_refresh")
    resp = client.post(REFRESH, headers=_csrf(client))
    assert resp.status_code == 204
    new_refresh = _set_cookie(resp, "tm_refresh")
    assert new_refresh and new_refresh != old_refresh
    assert _set_cookie(resp, "tm_access")
    assert client.get(ME).status_code == 200

    row = db.query(UserSession).one()
    assert row.refresh_hash == session_store.hash_token(new_refresh)
    assert row.prev_refresh_hash == session_store.hash_token(old_refresh)


def test_two_tabs_refreshing_at_once_do_not_log_each_other_out(client, logged_in, db):
    """Both present the same old token; the second must be tolerated."""
    old_refresh = _set_cookie(logged_in[2], "tm_refresh")
    csrf = client.cookies.get("tm_csrf")

    first = _refresh_with(client, old_refresh, csrf)
    second = _refresh_with(client, old_refresh, csrf)  # the loser of the race
    assert first.status_code == 204 and second.status_code == 204
    # the loser gets a new access cookie but must NOT overwrite the winner's refresh cookie
    assert _set_cookie(second, "tm_refresh") is None
    assert _set_cookie(second, "tm_access")

    winners_refresh = _set_cookie(first, "tm_refresh")
    assert _refresh_with(client, winners_refresh, csrf).status_code == 204
    assert db.query(UserSession).one().revoked_at is None


def test_replaying_a_rotated_token_after_the_grace_window_revokes_the_session(
    client, logged_in, db, monkeypatch
):
    monkeypatch.setattr(settings, "SESSION_REFRESH_GRACE_SECONDS", 0)
    old_access = logged_in[2].json()["access_token"]
    old_refresh = _set_cookie(logged_in[2], "tm_refresh")
    csrf = client.cookies.get("tm_csrf")
    assert _refresh_with(client, old_refresh, csrf).status_code == 204  # legitimate rotation

    replay = _refresh_with(client, old_refresh, csrf)  # attacker (or stale copy) replays the old one
    assert replay.status_code == 401
    assert db.query(UserSession).one().revoked_at is not None
    # even the access token issued before is dead now
    assert TestClient(app).get(ME, headers={"Authorization": f"Bearer {old_access}"}).status_code == 401


# ------------------------------------------------------------ session lifetime

def test_idle_session_cannot_refresh(client, logged_in, db):
    db.query(UserSession).update(
        {"last_used_at": datetime.now(timezone.utc) - timedelta(minutes=settings.SESSION_IDLE_MINUTES + 1)}
    )
    db.commit()
    assert client.post(REFRESH, headers=_csrf(client)).status_code == 401
    assert db.query(UserSession).one().revoked_at is not None


def test_session_past_its_absolute_lifetime_is_dead_everywhere(client, logged_in, db):
    db.query(UserSession).update({"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)})
    db.commit()
    # the still-unexpired access cookie is rejected immediately...
    assert client.get(ME).status_code == 401
    # ...and so is renewing it
    assert client.post(REFRESH, headers=_csrf(client)).status_code == 401


def test_deactivated_user_cannot_refresh(client, logged_in, db):
    user = logged_in[0]
    db.query(User).filter(User.id == user.id).update({"is_active": False})
    db.commit()
    assert client.post(REFRESH, headers=_csrf(client)).status_code == 401
    assert db.query(UserSession).one().revoked_at is not None


def test_failed_refresh_clears_the_cookies(client, logged_in, db):
    db.query(UserSession).update({"revoked_at": datetime.now(timezone.utc)})
    db.commit()
    resp = client.post(REFRESH, headers=_csrf(client))
    assert resp.status_code == 401
    for name in ("tm_access", "tm_refresh", "tm_csrf"):
        assert 'max-age=0' in _set_cookie_header(resp, name).lower()


# ----------------------------------------------------------------- logout

def test_logout_revokes_the_session_and_clears_cookies(client, logged_in, db):
    access = logged_in[2].json()["access_token"]
    resp = client.post(LOGOUT)
    assert resp.status_code == 204
    assert db.query(UserSession).one().revoked_at is not None
    assert client.post(REFRESH, headers={"X-CSRF-Token": "x"}).status_code in (401, 403)
    assert client.get(ME).status_code == 401
    # the access token that was in use is revoked too
    assert TestClient(app).get(ME, headers={"Authorization": f"Bearer {access}"}).status_code == 401


def test_logout_works_with_only_the_refresh_cookie(client, logged_in, db):
    """Access cookie already expired (15 min), user clicks Log out: it must
    really end the session, not leave a refresh cookie that logs them back in."""
    refresh = _set_cookie(logged_in[2], "tm_refresh")
    csrf = client.cookies.get("tm_csrf")
    resp = client.post(LOGOUT, headers={"Cookie": f"tm_refresh={refresh}"})
    assert resp.status_code == 204
    assert db.query(UserSession).one().revoked_at is not None
    assert _refresh_with(client, refresh, csrf).status_code == 401


def test_logout_without_any_credentials_is_401(client):
    assert client.post(LOGOUT).status_code == 401


def test_logout_all_ends_every_session_of_the_user(client, logged_in, db):
    user, password, _ = logged_in
    other = TestClient(app)
    _login(other, user, password)
    assert db.query(UserSession).filter(UserSession.revoked_at.is_(None)).count() == 2

    assert client.post(LOGOUT_ALL, headers=_csrf(client)).status_code == 204
    assert db.query(UserSession).filter(UserSession.revoked_at.is_(None)).count() == 0
    assert other.get(ME).status_code == 401
    assert other.post(REFRESH, headers=_csrf(other)).status_code == 401


def test_each_login_is_its_own_session(client, make_user, db):
    user, password = make_user()
    a, b = TestClient(app), TestClient(app)
    _login(a, user, password)
    _login(b, user, password)
    assert db.query(UserSession).filter(UserSession.user_id == user.id).count() == 2
    # logging out of one leaves the other alone
    assert a.post(LOGOUT).status_code == 204
    assert a.get(ME).status_code == 401
    assert b.get(ME).status_code == 200


# ------------------------------------------------------ housekeeping and config

def test_purge_removes_only_dead_sessions(make_user, db):
    user, _ = make_user()
    live, _ = session_store.create_session(db, user.id, None, None)
    expired, _ = session_store.create_session(db, user.id, None, None)
    expired.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    assert session_store.purge_expired_sessions(db) == 1
    assert [r.id for r in db.query(UserSession).all()] == [live.id]


def test_cleanup_task_is_registered_and_scheduled():
    from app.core.celery_app import celery_app
    import app.core.auth_cleanup  # noqa: F401  (registers the task)

    assert "auth_cleanup.purge" in celery_app.tasks
    assert any(e["task"] == "auth_cleanup.purge" for e in celery_app.conf.beat_schedule.values())


def test_production_refuses_insecure_cookies():
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        Settings(ENV="production", DEBUG=False, JWT_SECRET_KEY="x" * 40, COOKIE_SECURE=False)


def test_cookies_are_secure_by_default_only_in_production():
    assert Settings(ENV="production", DEBUG=False, JWT_SECRET_KEY="x" * 40).COOKIES_SECURE is True
    assert Settings(ENV="development").COOKIES_SECURE is False
