import pytest
from app.core import security as security_module
from app.models.user import UserRole

# ---------------------------------------------------------------------------
# POST /api/auth/register
# ---------------------------------------------------------------------------

def test_register_defaults_to_user_role(client):
    resp = client.post("/api/auth/register", json={"email": "new@test.com", "password": "pass1234"})
    assert resp.status_code == 201
    assert resp.json()["role"] == UserRole.USER.value

def test_register_is_active_immediately(client):
    """New signups can log in right away — see models/user.py's is_active
    default and the migration that flipped the DB server_default to match.
    No admin approval step gates login itself; approval only gates
    promotion to RECRUITER (see test_register_recruiter_request_stays_user_until_approved
    below)."""
    resp = client.post("/api/auth/register", json={"email": "active@test.com", "password": "pass1234"})
    assert resp.status_code == 201
    assert resp.json()["is_active"] is True

def test_register_duplicate_email_rejected(client, make_user):
    user, _ = make_user()
    resp = client.post("/api/auth/register", json={"email": user.email, "password": "whatever123"})
    assert resp.status_code == 400

def test_register_recruiter_request_stays_user_until_approved(client):
    """Signing up asking for RECRUITER never grants it directly — role
    stays USER, the ask is only recorded in requested_role (see auth.py's
    comment on this: 'Signup never writes role=RECRUITER directly')."""
    resp = client.post(
        "/api/auth/register",
        json={"email": "wannabe-recruiter@test.com", "password": "pass1234", "role": "recruiter"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == UserRole.USER.value
    assert body["requested_role"] == UserRole.RECRUITER.value

@pytest.mark.parametrize("role", ["admin", "superuser"])
def test_register_cannot_request_admin_or_superuser(client, role):
    resp = client.post(
        "/api/auth/register",
        json={"email": f"sneaky-{role}@test.com", "password": "pass1234", "role": role},
    )
    assert resp.status_code == 422

@pytest.mark.parametrize("password", [
    "short1",              # under 8 chars
    "alllettersnodigits",  # no number
    "12345678",            # no letter
])
def test_register_rejects_weak_password(client, password):
    resp = client.post("/api/auth/register", json={"email": "weak@test.com", "password": password})
    assert resp.status_code == 422

def test_register_accepts_8_char_password_with_letter_and_number(client):
    """Matches the current backend rule in schemas/user.py::
    _validate_password_strength — 8 chars minimum, at least one letter and
    one number."""
    resp = client.post("/api/auth/register", json={"email": "justright@test.com", "password": "abcd1234"})
    assert resp.status_code == 201

def test_register_invalid_email_rejected(client):
    resp = client.post("/api/auth/register", json={"email": "not-an-email", "password": "pass1234"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

def test_login_success_returns_token(client, make_user):
    user, password = make_user()
    resp = client.post("/api/auth/login", data={"username": user.email, "password": password})
    assert resp.status_code == 200
    assert "access_token" in resp.json()

def test_login_wrong_password_rejected(client, make_user):
    user, _ = make_user()
    resp = client.post("/api/auth/login", data={"username": user.email, "password": "wrongpass"})
    assert resp.status_code == 401

def test_login_unknown_email_rejected(client):
    resp = client.post("/api/auth/login", data={"username": "nobody@test.com", "password": "whatever123"})
    assert resp.status_code == 401

def test_login_inactive_user_rejected(client, make_user):
    """The remaining, real use of is_active: an explicitly deactivated
    account is blocked at login, distinct from a bad password (403, not
    401) — see auth.py's login route."""
    user, password = make_user(is_active=False)
    resp = client.post("/api/auth/login", data={"username": user.email, "password": password})
    assert resp.status_code == 403

def test_login_lockout_after_repeated_failures(client, make_user):
    """core/security.py locks an email out after 5 failed attempts within
    the window. Verifies both the trigger and that a *correct* password no
    longer works once locked (429, not 200)."""
    user, password = make_user()
    for _ in range(5):
        resp = client.post("/api/auth/login", data={"username": user.email, "password": "wrong"})
        assert resp.status_code == 401
    resp = client.post("/api/auth/login", data={"username": user.email, "password": password})
    assert resp.status_code == 429

def test_login_success_clears_failed_attempts(client, make_user):
    """A successful login resets the counter — a few wrong guesses
    followed by the right password shouldn't count toward lockout."""
    user, password = make_user()
    for _ in range(3):
        client.post("/api/auth/login", data={"username": user.email, "password": "wrong"})
    resp = client.post("/api/auth/login", data={"username": user.email, "password": password})
    assert resp.status_code == 200
    # confirm the counter was actually cleared, not just coincidentally
    # under the limit
    assert user.email not in security_module._failed_attempts


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------

def test_logout_blacklists_token(client, make_user, auth_headers):
    user, _ = make_user()
    headers = auth_headers(user)
    resp = client.post("/api/auth/logout", headers=headers)
    assert resp.status_code == 204
    # the same token must now be rejected by any protected endpoint
    resp = client.get("/api/users/me", headers=headers)
    assert resp.status_code == 401

def test_logout_requires_auth(client):
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/auth/change-password
# ---------------------------------------------------------------------------

def test_change_password_success(client, make_user, auth_headers):
    user, password = make_user()
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": password, "new_password": "brandnew123"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 204
    # old password no longer works, new one does
    assert client.post("/api/auth/login", data={"username": user.email, "password": password}).status_code == 401
    assert client.post("/api/auth/login", data={"username": user.email, "password": "brandnew123"}).status_code == 200

def test_change_password_wrong_current_password_rejected(client, make_user, auth_headers):
    user, _ = make_user()
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "totallywrong", "new_password": "brandnew123"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 400

def test_change_password_rejects_weak_new_password(client, make_user, auth_headers):
    user, password = make_user()
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": password, "new_password": "short1"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 422

def test_change_password_requires_auth(client):
    resp = client.post(
        "/api/auth/change-password",
        json={"current_password": "whatever1", "new_password": "brandnew123"},
    )
    assert resp.status_code == 401