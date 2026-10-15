import pytest
from sqlalchemy.exc import IntegrityError
from app.models.user import UserRole


# ---------------------------------------------------------------------------
# GET /api/users — access control and the schema trim by viewer role
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role,expected_status", [
    (UserRole.USER, 403),
    (UserRole.RECRUITER, 403),
    (UserRole.ADMIN, 200),
    (UserRole.SUPERUSER, 200),
])
def test_list_users_access(client, make_user, auth_headers, role, expected_status):
    user, _ = make_user(role=role)
    resp = client.get("/api/users", headers=auth_headers(user))
    assert resp.status_code == expected_status


def test_recruiter_cannot_fetch_a_user(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    other, _ = make_user(role=UserRole.USER)
    resp = client.get(f"/api/users/{other.id}", headers=auth_headers(recruiter))
    assert resp.status_code == 403


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

def test_activating_never_grants_a_requested_role(client, make_user, auth_headers):
    """Role grants are the superuser's call alone (POST .../approve-request);
    flipping is_active, even by an admin of the same sub company, must not
    smuggle one in."""
    admin, _ = make_user(role=UserRole.ADMIN)
    pending_user, _ = make_user(requested_role=UserRole.RECRUITER, is_active=False)
    resp = client.patch(
        f"/api/users/{pending_user.id}/active",
        json={"is_active": True},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == UserRole.USER.value
    assert body["is_active"] is True
    assert body["requested_role"] == UserRole.RECRUITER.value

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
    # An admin can't even see the superuser (they sit outside every sub company)...
    resp = client.patch(
        f"/api/users/{superuser.id}/active",
        json={"is_active": False},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 404
    # ...and the superuser can't switch themselves off either.
    resp = client.patch(
        f"/api/users/{superuser.id}/active",
        json={"is_active": False},
        headers=auth_headers(superuser),
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
    admin, _ = make_user(role=UserRole.SUPERUSER)
    pending_user, _ = make_user(requested_role=UserRole.RECRUITER)
    resp = client.post(
        f"/api/users/{pending_user.id}/reject-recruiter-request",
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["requested_role"] is None
    assert body["role"] == UserRole.USER.value
    assert body["is_active"] is True  # rejection doesn't touch is_active either way — it defaults True regardless

    db.expire_all()
    refreshed = db.get(type(pending_user), pending_user.id)
    assert refreshed.recruiter_rejected_at is not None


def test_reject_without_pending_request_is_400(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.SUPERUSER)
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
    admin, _ = make_user(role=UserRole.SUPERUSER)
    user, _ = make_user(requested_role=UserRole.RECRUITER)
    client.post(f"/api/users/{user.id}/reject-recruiter-request", headers=auth_headers(admin))

    # Simulate the request being made again, committed through the same
    # session `db` uses — this is the session the API's dependency override
    # actually reads from, so the change is visible to the next request.
    db.expire_all()
    fresh = db.get(type(user), user.id)
    fresh.requested_role = UserRole.RECRUITER
    db.commit()

    resp = client.post(f"/api/users/{user.id}/approve-request", headers=auth_headers(admin))
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
    assert resp.status_code == 404


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


# ---------------------------------------------------------------------------
# POST /api/users/{id}/approve-recruiter-request — counterpart to reject
# ---------------------------------------------------------------------------

def _audit_rows_for(db, user_id):
    from app.models.audit_log import AuditLog
    db.expire_all()
    return db.query(AuditLog).filter(AuditLog.resource_id == user_id).all()


def test_approve_promotes_to_recruiter_and_clears_request(client, make_user, auth_headers, db):
    actor, _ = make_user(role=UserRole.SUPERUSER)
    pending, _ = make_user(requested_role=UserRole.RECRUITER)
    resp = client.post(
        f"/api/users/{pending.id}/approve-recruiter-request",
        headers=auth_headers(actor),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == UserRole.RECRUITER.value
    assert body["requested_role"] is None
    assert body["is_active"] is True

    db.expire_all()
    refreshed = db.get(type(pending), pending.id)
    assert refreshed.role == UserRole.RECRUITER
    assert refreshed.requested_role is None


def test_approve_reactivates_an_inactive_account(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.SUPERUSER)
    pending, _ = make_user(requested_role=UserRole.RECRUITER, is_active=False)
    resp = client.post(
        f"/api/users/{pending.id}/approve-recruiter-request",
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    db.expire_all()
    assert db.get(type(pending), pending.id).is_active is True


def test_approve_clears_an_earlier_rejection_stamp(client, make_user, auth_headers, db):
    from datetime import datetime, timezone
    admin, _ = make_user(role=UserRole.SUPERUSER)
    pending, _ = make_user(requested_role=UserRole.RECRUITER)
    pending.recruiter_rejected_at = datetime.now(timezone.utc)
    db.commit()

    resp = client.post(
        f"/api/users/{pending.id}/approve-recruiter-request",
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    db.expire_all()
    assert db.get(type(pending), pending.id).recruiter_rejected_at is None


def test_approved_user_gains_recruiter_access(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.SUPERUSER)
    pending, _ = make_user(requested_role=UserRole.RECRUITER)
    # GET /api/audit is recruiter/admin only; a plain user is refused.
    assert client.get("/api/audit", headers=auth_headers(pending)).status_code == 403

    client.post(f"/api/users/{pending.id}/approve-recruiter-request", headers=auth_headers(admin))
    assert client.get("/api/audit", headers=auth_headers(pending)).status_code == 200


def test_approve_writes_one_audit_entry_without_the_password_hash(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.SUPERUSER)
    pending, _ = make_user(requested_role=UserRole.RECRUITER)
    client.post(f"/api/users/{pending.id}/approve-recruiter-request", headers=auth_headers(admin))

    rows = _audit_rows_for(db, pending.id)
    assert len(rows) == 1
    entry = rows[0]
    assert (entry.action, entry.resource_type) == ("update", "user")
    assert entry.actor_id == admin.id
    assert entry.before["role"] == UserRole.USER.value
    assert entry.before["requested_role"] == UserRole.RECRUITER.value
    assert entry.after["role"] == UserRole.RECRUITER.value
    assert entry.after["requested_role"] is None
    assert "hashed_password" not in entry.before and "hashed_password" not in entry.after


def test_approve_without_pending_request_is_400_and_audits_nothing(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.SUPERUSER)
    plain_user, _ = make_user()
    resp = client.post(
        f"/api/users/{plain_user.id}/approve-recruiter-request",
        headers=auth_headers(admin),
    )
    assert resp.status_code == 400
    assert _audit_rows_for(db, plain_user.id) == []


@pytest.mark.parametrize("role", [UserRole.RECRUITER, UserRole.ADMIN, UserRole.SUPERUSER])
def test_approve_never_changes_a_non_user_account(client, make_user, auth_headers, db, role):
    """A pending request on an account that is already a recruiter/admin/
    superuser must be refused, so approval can never demote or alter it."""
    actor, _ = make_user(role=UserRole.SUPERUSER)
    if role == UserRole.SUPERUSER:
        # there is only ever one superuser, so the actor is also the target
        actor.requested_role = UserRole.RECRUITER
        db.commit()
        target = actor
    else:
        target, _ = make_user(role=role, requested_role=UserRole.RECRUITER)
    resp = client.post(
        f"/api/users/{target.id}/approve-recruiter-request",
        headers=auth_headers(actor),
    )
    assert resp.status_code == 400
    db.expire_all()
    refreshed = db.get(type(target), target.id)
    assert refreshed.role == role
    assert refreshed.requested_role == UserRole.RECRUITER
    assert _audit_rows_for(db, target.id) == []


def test_approving_twice_second_call_is_400(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.SUPERUSER)
    pending, _ = make_user(requested_role=UserRole.RECRUITER)
    url = f"/api/users/{pending.id}/approve-recruiter-request"
    assert client.post(url, headers=auth_headers(admin)).status_code == 200
    assert client.post(url, headers=auth_headers(admin)).status_code == 400


def test_cannot_approve_a_request_that_was_already_rejected(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.SUPERUSER)
    pending, _ = make_user(requested_role=UserRole.RECRUITER)
    client.post(f"/api/users/{pending.id}/reject-recruiter-request", headers=auth_headers(admin))
    resp = client.post(
        f"/api/users/{pending.id}/approve-recruiter-request",
        headers=auth_headers(admin),
    )
    assert resp.status_code == 400


def test_approve_unknown_user_is_404(client, make_user, auth_headers):
    import uuid
    admin, _ = make_user(role=UserRole.SUPERUSER)
    resp = client.post(
        f"/api/users/{uuid.uuid4()}/approve-recruiter-request",
        headers=auth_headers(admin),
    )
    assert resp.status_code == 404


def test_approve_malformed_id_is_422(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.SUPERUSER)
    resp = client.post(
        "/api/users/not-a-uuid/approve-recruiter-request",
        headers=auth_headers(admin),
    )
    assert resp.status_code == 422


def test_approve_requires_authentication(client, make_user):
    pending, _ = make_user(requested_role=UserRole.RECRUITER)
    resp = client.post(f"/api/users/{pending.id}/approve-recruiter-request")
    assert resp.status_code == 401


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER, UserRole.ADMIN])
def test_approve_forbidden_for_everyone_but_the_superuser(client, make_user, auth_headers, db, role):
    actor, _ = make_user(role=role)
    pending, _ = make_user(requested_role=UserRole.RECRUITER)
    resp = client.post(
        f"/api/users/{pending.id}/approve-recruiter-request",
        headers=auth_headers(actor),
    )
    assert resp.status_code == 403
    db.expire_all()
    refreshed = db.get(type(pending), pending.id)
    assert refreshed.role == UserRole.USER
    assert refreshed.requested_role == UserRole.RECRUITER


def test_approve_forbidden_for_a_deactivated_admin(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN, is_active=False)
    pending, _ = make_user(requested_role=UserRole.RECRUITER)
    resp = client.post(
        f"/api/users/{pending.id}/approve-recruiter-request",
        headers=auth_headers(admin),
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/users/{id} and PATCH /api/users/{id}
# ---------------------------------------------------------------------------

_PUBLIC_FIELDS = {"id", "email", "role", "full_name"}
_ADMIN_ONLY_FIELDS = {"is_active", "requested_role", "recruiter_rejected_at", "phone", "company", "created_at"}


def test_get_user_requires_authentication(client, make_user):
    target, _ = make_user()
    assert client.get(f"/api/users/{target.id}").status_code == 401


def test_get_user_forbidden_for_plain_users(client, make_user, auth_headers):
    actor, _ = make_user(role=UserRole.USER)
    target, _ = make_user()
    assert client.get(f"/api/users/{target.id}", headers=auth_headers(actor)).status_code == 403


def test_recruiter_gets_the_trimmed_public_view(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    target, _ = make_user()
    resp = client.get(f"/api/users/{target.id}", headers=auth_headers(recruiter))
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == _PUBLIC_FIELDS
    assert body["id"] == str(target.id) and body["email"] == target.email


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERUSER])
def test_admin_and_superuser_get_the_full_view(client, make_user, auth_headers, role):
    actor, _ = make_user(role=role)
    target, _ = make_user(requested_role=UserRole.RECRUITER)
    resp = client.get(f"/api/users/{target.id}", headers=auth_headers(actor))
    assert resp.status_code == 200
    body = resp.json()
    assert _PUBLIC_FIELDS | _ADMIN_ONLY_FIELDS <= set(body)
    assert body["requested_role"] == UserRole.RECRUITER.value


@pytest.mark.parametrize("role", [UserRole.RECRUITER, UserRole.ADMIN])
def test_get_user_never_leaks_the_password_hash(client, make_user, auth_headers, role):
    actor, _ = make_user(role=role)
    target, _ = make_user()
    resp = client.get(f"/api/users/{target.id}", headers=auth_headers(actor))
    assert "hashed_password" not in resp.text and target.email in resp.text


def test_get_unknown_user_is_404(client, make_user, auth_headers):
    import uuid
    admin, _ = make_user(role=UserRole.ADMIN)
    assert client.get(f"/api/users/{uuid.uuid4()}", headers=auth_headers(admin)).status_code == 404


def test_get_user_malformed_id_is_422(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    assert client.get("/api/users/not-a-uuid", headers=auth_headers(admin)).status_code == 422


_PROFILE = {
    "full_name": "Ada Lovelace",
    "phone": "+1 555 0100",
    "company": "Analytical Engines",
    "title": "Engineer",
    "skills": ["python", "math"],
    "experience_years": 7,
    "location": "London",
    "desired_role": "Lead",
}


@pytest.mark.parametrize("target_role", [UserRole.USER, UserRole.RECRUITER])
def test_admin_can_edit_user_and_recruiter_profiles(client, make_user, auth_headers, db, target_role):
    admin, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user(role=target_role)
    resp = client.patch(f"/api/users/{target.id}", json=_PROFILE, headers=auth_headers(admin))
    assert resp.status_code == 200
    body = resp.json()
    for field, value in _PROFILE.items():
        assert body[field] == value

    db.expire_all()
    refreshed = db.get(type(target), target.id)
    assert refreshed.full_name == "Ada Lovelace" and refreshed.skills == ["python", "math"]


@pytest.mark.parametrize("target_role", [UserRole.ADMIN, UserRole.SUPERUSER])
def test_admin_cannot_edit_admins_or_the_superuser(client, make_user, auth_headers, db, target_role):
    actor, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user(role=target_role)
    resp = client.patch(f"/api/users/{target.id}", json={"full_name": "Hacked"}, headers=auth_headers(actor))
    # another admin in the same company: forbidden; the superuser: not visible at all
    assert resp.status_code == (403 if target_role == UserRole.ADMIN else 404)
    db.expire_all()
    assert db.get(type(target), target.id).full_name != "Hacked"


def test_admin_cannot_use_this_route_on_themselves(client, make_user, auth_headers):
    """An admin edits their own profile through PATCH /api/users/me."""
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.patch(f"/api/users/{admin.id}", json={"full_name": "Me"}, headers=auth_headers(admin))
    assert resp.status_code == 403


@pytest.mark.parametrize("target_role", [UserRole.USER, UserRole.RECRUITER, UserRole.ADMIN])
def test_superuser_can_edit_anyone(client, make_user, auth_headers, target_role):
    superuser, _ = make_user(role=UserRole.SUPERUSER)
    target, _ = make_user(role=target_role)
    resp = client.patch(f"/api/users/{target.id}", json={"full_name": "Edited"}, headers=auth_headers(superuser))
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Edited"


def test_superuser_can_edit_their_own_profile_here(client, make_user, auth_headers):
    superuser, _ = make_user(role=UserRole.SUPERUSER)
    resp = client.patch(f"/api/users/{superuser.id}", json={"title": "Boss"}, headers=auth_headers(superuser))
    assert resp.status_code == 200 and resp.json()["title"] == "Boss"


def test_patch_cannot_change_role_status_or_email(client, make_user, auth_headers, db):
    """UserProfileUpdate has no role/is_active/email/requested_role, so those
    keys in the body are ignored — they have their own endpoints."""
    admin, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user()
    email_before = target.email
    resp = client.patch(
        f"/api/users/{target.id}",
        json={
            "full_name": "Renamed",
            "role": "admin",
            "is_active": False,
            "email": "hijack@test.com",
            "requested_role": "recruiter",
        },
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    db.expire_all()
    refreshed = db.get(type(target), target.id)
    assert refreshed.full_name == "Renamed"
    assert refreshed.role == UserRole.USER
    assert refreshed.is_active is True
    assert refreshed.email == email_before
    assert refreshed.requested_role is None


def test_patch_only_touches_the_fields_sent(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user()
    client.patch(f"/api/users/{target.id}", json={"company": "Acme"}, headers=auth_headers(admin))
    client.patch(f"/api/users/{target.id}", json={"title": "CTO"}, headers=auth_headers(admin))
    db.expire_all()
    refreshed = db.get(type(target), target.id)
    assert (refreshed.company, refreshed.title) == ("Acme", "CTO")


def test_patch_with_explicit_null_clears_a_field(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user()
    client.patch(f"/api/users/{target.id}", json={"company": "Acme"}, headers=auth_headers(admin))
    resp = client.patch(f"/api/users/{target.id}", json={"company": None}, headers=auth_headers(admin))
    assert resp.status_code == 200 and resp.json()["company"] is None


def test_patch_with_empty_body_changes_nothing_and_audits_nothing(client, make_user, auth_headers, db):
    from app.models.audit_log import AuditLog
    admin, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user()
    resp = client.patch(f"/api/users/{target.id}", json={}, headers=auth_headers(admin))
    assert resp.status_code == 200
    db.expire_all()
    assert db.query(AuditLog).filter(AuditLog.resource_id == target.id).count() == 0


def test_patch_writes_an_audit_entry_without_the_password_hash(client, make_user, auth_headers, db):
    from app.models.audit_log import AuditLog
    admin, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user()
    client.patch(f"/api/users/{target.id}", json={"full_name": "Audited"}, headers=auth_headers(admin))
    db.expire_all()
    rows = db.query(AuditLog).filter(AuditLog.resource_id == target.id).all()
    assert len(rows) == 1
    entry = rows[0]
    assert (entry.action, entry.resource_type, entry.actor_id) == ("update", "user", admin.id)
    assert entry.before["full_name"] != "Audited" and entry.after["full_name"] == "Audited"
    assert "hashed_password" not in entry.before and "hashed_password" not in entry.after


@pytest.mark.parametrize("body", [
    {"skills": "python"},
    {"experience_years": "lots"},
    {"full_name": ["a"]},
])
def test_patch_rejects_wrongly_typed_fields(client, make_user, auth_headers, body):
    admin, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user()
    resp = client.patch(f"/api/users/{target.id}", json=body, headers=auth_headers(admin))
    assert resp.status_code == 422


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER])
def test_patch_forbidden_for_non_admins(client, make_user, auth_headers, db, role):
    actor, _ = make_user(role=role)
    target, _ = make_user()
    resp = client.patch(f"/api/users/{target.id}", json={"full_name": "Nope"}, headers=auth_headers(actor))
    assert resp.status_code == 403
    db.expire_all()
    assert db.get(type(target), target.id).full_name != "Nope"


def test_patch_requires_authentication(client, make_user):
    target, _ = make_user()
    assert client.patch(f"/api/users/{target.id}", json={"full_name": "x"}).status_code == 401


def test_patch_unknown_user_is_404(client, make_user, auth_headers):
    import uuid
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.patch(f"/api/users/{uuid.uuid4()}", json={"full_name": "x"}, headers=auth_headers(admin))
    assert resp.status_code == 404


def test_patch_malformed_id_is_422(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.patch("/api/users/not-a-uuid", json={"full_name": "x"}, headers=auth_headers(admin))
    assert resp.status_code == 422