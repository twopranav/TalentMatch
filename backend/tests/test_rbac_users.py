"""
Rewrite note: the previous version of this file tested a hierarchy that
doesn't match the actual code — it assumed ADMIN was a unique singleton
role (`test_only_one_admin_ever_exists`, expecting IntegrityError on a
second ADMIN) and called endpoints that don't exist (`PATCH .../role`,
`POST .../transfer-admin`). The real model, per models/user.py's own
docstring, is: SUPERUSER is the singleton (enforced by a DB partial unique
index), ADMIN allows many, and the real endpoints are `/admin-status` and
`/transfer-superuser`. This file tests that actual hierarchy instead.
"""
import pytest
from sqlalchemy.exc import IntegrityError
from app.models.user import UserRole


# ---------------------------------------------------------------------------
# GET /api/users — access control and the schema trim by viewer role
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role,expected_status", [
    (UserRole.USER, 403),
    (UserRole.RECRUITER, 200),
    (UserRole.ADMIN, 200),
    (UserRole.SUPERUSER, 200),
])
def test_list_users_access(client, make_user, auth_headers, role, expected_status):
    user, _ = make_user(role=role)
    resp = client.get("/api/users", headers=auth_headers(user))
    assert resp.status_code == expected_status


def test_recruiter_gets_trimmed_schema(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    make_user(role=UserRole.USER)
    resp = client.get("/api/users", headers=auth_headers(recruiter))
    assert "created_at" not in resp.json()[0]


def test_admin_gets_full_schema(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.get("/api/users", headers=auth_headers(admin))
    assert "created_at" in resp.json()[0]


# ---------------------------------------------------------------------------
# GET /api/users?pending=true — new: surfacing pending recruiter requests
# ---------------------------------------------------------------------------

def test_pending_filter_shows_only_requested_recruiters(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    make_user(role=UserRole.USER)  # no request — should not appear
    pending_user, _ = make_user(requested_role=UserRole.RECRUITER)
    resp = client.get("/api/users?pending=true", headers=auth_headers(admin))
    assert resp.status_code == 200
    ids = [u["id"] for u in resp.json()]
    assert ids == [str(pending_user.id)]


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER])
def test_pending_filter_forbidden_for_non_admins(client, make_user, auth_headers, role):
    actor, _ = make_user(role=role)
    resp = client.get("/api/users?pending=true", headers=auth_headers(actor))
    assert resp.status_code == 403


def test_pending_filter_empty_when_nothing_pending(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    make_user(role=UserRole.USER)
    resp = client.get("/api/users?pending=true", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# PATCH /api/users/{id}/active — approval, and the auto-promotion side effect
# ---------------------------------------------------------------------------

def test_activating_pending_recruiter_promotes_role(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    pending_user, _ = make_user(requested_role=UserRole.RECRUITER)
    resp = client.patch(
        f"/api/users/{pending_user.id}/active",
        json={"is_active": True},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == UserRole.RECRUITER.value
    assert body["is_active"] is True
    assert body["requested_role"] is None


def test_activating_plain_user_does_not_change_role(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    plain_user, _ = make_user()  # no requested_role
    resp = client.patch(
        f"/api/users/{plain_user.id}/active",
        json={"is_active": True},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == UserRole.USER.value


def test_deactivating_does_not_touch_role(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    recruiter, _ = make_user(role=UserRole.RECRUITER, is_active=True)
    resp = client.patch(
        f"/api/users/{recruiter.id}/active",
        json={"is_active": False},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == UserRole.RECRUITER.value
    assert resp.json()["is_active"] is False


def test_cannot_change_active_status_of_superuser(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    superuser, _ = make_user(role=UserRole.SUPERUSER, is_active=True)
    resp = client.patch(
        f"/api/users/{superuser.id}/active",
        json={"is_active": False},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER])
def test_active_patch_forbidden_for_non_admins(client, make_user, auth_headers, role):
    actor, _ = make_user(role=role)
    target, _ = make_user()
    resp = client.patch(
        f"/api/users/{target.id}/active",
        json={"is_active": True},
        headers=auth_headers(actor),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/users/{id}/reject-recruiter-request — new: explicit denial
# ---------------------------------------------------------------------------

def test_reject_clears_pending_request_without_changing_role(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.ADMIN)
    pending_user, _ = make_user(requested_role=UserRole.RECRUITER)
    resp = client.post(
        f"/api/users/{pending_user.id}/reject-recruiter-request",
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["requested_role"] is None
    assert body["role"] == UserRole.USER.value
    assert body["is_active"] is False  # rejection doesn't activate them either

    db.expire_all()
    refreshed = db.get(type(pending_user), pending_user.id)
    assert refreshed.recruiter_rejected_at is not None


def test_reject_without_pending_request_is_400(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    plain_user, _ = make_user()  # nothing pending
    resp = client.post(
        f"/api/users/{plain_user.id}/reject-recruiter-request",
        headers=auth_headers(admin),
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER])
def test_reject_forbidden_for_non_admins(client, make_user, auth_headers, role):
    actor, _ = make_user(role=role)
    pending_user, _ = make_user(requested_role=UserRole.RECRUITER)
    resp = client.post(
        f"/api/users/{pending_user.id}/reject-recruiter-request",
        headers=auth_headers(actor),
    )
    assert resp.status_code == 403


def test_rejected_then_reregistered_recruiter_request_can_still_be_approved(client, make_user, auth_headers, db):
    """A user rejected once isn't permanently blocked — if requested_role
    gets set again (e.g. a future 're-apply' flow, or an admin correcting
    a mistaken rejection), approval still works. This guards against the
    reject action accidentally leaving stale state that blocks a future
    legitimate request."""
    admin, _ = make_user(role=UserRole.ADMIN)
    user, _ = make_user(requested_role=UserRole.RECRUITER)
    client.post(f"/api/users/{user.id}/reject-recruiter-request", headers=auth_headers(admin))

    # Simulate the request being made again, committed through the same
    # session `db` uses — this is the session the API's dependency override
    # actually reads from, so the change is visible to the next request.
    db.expire_all()
    fresh = db.get(type(user), user.id)
    fresh.requested_role = UserRole.RECRUITER
    db.commit()

    resp = client.patch(
        f"/api/users/{user.id}/active",
        json={"is_active": True},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == UserRole.RECRUITER.value


# ---------------------------------------------------------------------------
# PATCH /api/users/{id}/admin-status — superuser-only ADMIN promotion/demotion
# ---------------------------------------------------------------------------

def test_superuser_can_promote_user_to_admin(client, make_user, auth_headers):
    superuser, _ = make_user(role=UserRole.SUPERUSER, is_active=True)
    target, _ = make_user(role=UserRole.USER)
    resp = client.patch(
        f"/api/users/{target.id}/admin-status",
        json={"role": "admin"},
        headers=auth_headers(superuser),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == UserRole.ADMIN.value
    assert body["is_active"] is True  # promoted admins are activated immediately


def test_superuser_can_demote_admin_to_user(client, make_user, auth_headers):
    superuser, _ = make_user(role=UserRole.SUPERUSER, is_active=True)
    target, _ = make_user(role=UserRole.ADMIN, is_active=True)
    resp = client.patch(
        f"/api/users/{target.id}/admin-status",
        json={"role": "user"},
        headers=auth_headers(superuser),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == UserRole.USER.value


def test_admin_status_rejects_recruiter_as_target_value(client, make_user, auth_headers):
    superuser, _ = make_user(role=UserRole.SUPERUSER, is_active=True)
    target, _ = make_user(role=UserRole.USER)
    resp = client.patch(
        f"/api/users/{target.id}/admin-status",
        json={"role": "recruiter"},
        headers=auth_headers(superuser),
    )
    assert resp.status_code == 400


def test_admin_status_cannot_target_superuser(client, make_user, auth_headers):
    """
    Only one SUPERUSER can ever exist (enforced by the DB's partial unique
    index), and only a SUPERUSER can call this endpoint (require_superuser).
    So the only way to actually reach the "target is SUPERUSER" 400 is the
    superuser targeting themselves — there's no scenario where a second
    SUPERUSER row exists to target instead.
    """
    superuser, _ = make_user(role=UserRole.SUPERUSER, is_active=True)
    resp = client.patch(
        f"/api/users/{superuser.id}/admin-status",
        json={"role": "user"},
        headers=auth_headers(superuser),
    )
    assert resp.status_code == 400


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER, UserRole.ADMIN])
def test_admin_status_forbidden_for_non_superusers(client, make_user, auth_headers, role):
    """Confirms the model docstring's claim directly: 'no admin, however
    senior, can create or remove another admin' — only SUPERUSER can."""
    actor, _ = make_user(role=role, is_active=True)
    target, _ = make_user(role=UserRole.USER)
    resp = client.patch(
        f"/api/users/{target.id}/admin-status",
        json={"role": "admin"},
        headers=auth_headers(actor),
    )
    assert resp.status_code == 403


def test_multiple_admins_are_allowed(make_user):
    """Replaces the old (incorrect) test_only_one_admin_ever_exists — the
    model explicitly allows many admins; only SUPERUSER is a singleton."""
    make_user(role=UserRole.ADMIN)
    make_user(role=UserRole.ADMIN, email="second-admin@test.com")  # must not raise


def test_only_one_superuser_ever_exists(make_user):
    make_user(role=UserRole.SUPERUSER)
    with pytest.raises(IntegrityError):
        make_user(role=UserRole.SUPERUSER, email="second-su@test.com")


# ---------------------------------------------------------------------------
# POST /api/users/{id}/transfer-superuser
# ---------------------------------------------------------------------------

def test_transfer_superuser_swaps_roles_atomically(client, make_user, auth_headers, db):
    superuser, _ = make_user(role=UserRole.SUPERUSER, is_active=True)
    target, _ = make_user(role=UserRole.ADMIN, is_active=True)
    resp = client.post(f"/api/users/{target.id}/transfer-superuser", headers=auth_headers(superuser))
    assert resp.status_code == 200

    db.expire_all()
    # outgoing superuser is stripped all the way to USER, not ADMIN — per
    # the route's own docstring, this is deliberate, not a side effect
    assert db.get(type(superuser), superuser.id).role == UserRole.USER
    assert db.get(type(target), target.id).role == UserRole.SUPERUSER
    assert db.get(type(target), target.id).is_active is True


def test_transfer_superuser_cannot_target_self(client, make_user, auth_headers):
    superuser, _ = make_user(role=UserRole.SUPERUSER, is_active=True)
    resp = client.post(f"/api/users/{superuser.id}/transfer-superuser", headers=auth_headers(superuser))
    assert resp.status_code == 400


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER, UserRole.ADMIN])
def test_transfer_superuser_forbidden_for_non_superusers(client, make_user, auth_headers, role):
    actor, _ = make_user(role=role, is_active=True)
    target, _ = make_user(role=UserRole.USER)
    resp = client.post(f"/api/users/{target.id}/transfer-superuser", headers=auth_headers(actor))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/users/{id}
# ---------------------------------------------------------------------------

def test_admin_cannot_delete_superuser(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    superuser, _ = make_user(role=UserRole.SUPERUSER, is_active=True)
    resp = client.delete(f"/api/users/{superuser.id}", headers=auth_headers(admin))
    assert resp.status_code == 400


def test_admin_can_delete_other_admin(client, make_user, auth_headers):
    """Documenting real current behavior, not asserting it's the ideal
    design: delete_user only special-cases SUPERUSER targets, so one admin
    can delete another. Flag to the team if this should require SUPERUSER
    instead — that's a product decision, not something this test should
    silently paper over."""
    admin, _ = make_user(role=UserRole.ADMIN)
    other_admin, _ = make_user(role=UserRole.ADMIN, email="other-admin@test.com")
    resp = client.delete(f"/api/users/{other_admin.id}", headers=auth_headers(admin))
    assert resp.status_code == 204


def test_admin_can_delete_other_user(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user(role=UserRole.USER)
    resp = client.delete(f"/api/users/{target.id}", headers=auth_headers(admin))
    assert resp.status_code == 204


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER])
def test_delete_forbidden_for_non_admins(client, make_user, auth_headers, role):
    actor, _ = make_user(role=role)
    target, _ = make_user(role=UserRole.USER)
    resp = client.delete(f"/api/users/{target.id}", headers=auth_headers(actor))
    assert resp.status_code == 403