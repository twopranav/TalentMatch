import pytest
from sqlalchemy.exc import IntegrityError
from app.models.user import UserRole

@pytest.mark.parametrize("role,expected_status", [
    (UserRole.USER, 403),
    (UserRole.RECRUITER, 200),
    (UserRole.ADMIN, 200),
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

@pytest.mark.parametrize("role,expected_status", [
    (UserRole.USER, 403),
    (UserRole.RECRUITER, 403),
    (UserRole.ADMIN, 200),
])

def test_role_patch_access(client, make_user, auth_headers, role, expected_status):
    actor, _ = make_user(role=role)
    target, _ = make_user(role=UserRole.USER)
    resp = client.patch(f"/api/users/{target.id}/role", json={"role": "recruiter"}, headers=auth_headers(actor))
    assert resp.status_code == expected_status

def test_role_patch_rejects_admin_as_target_value(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user(role=UserRole.USER)
    resp = client.patch(f"/api/users/{target.id}/role", json={"role": "admin"}, headers=auth_headers(admin))
    assert resp.status_code == 400

def test_transfer_admin_swaps_roles_atomically(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.ADMIN)
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    resp = client.post(f"/api/users/{recruiter.id}/transfer-admin", headers=auth_headers(admin))
    assert resp.status_code == 200
    db.expire_all()
    assert db.get(type(admin), admin.id).role == UserRole.USER
    assert db.get(type(recruiter), recruiter.id).role == UserRole.ADMIN

def test_only_one_admin_ever_exists(make_user):
    make_user(role=UserRole.ADMIN)
    with pytest.raises(IntegrityError):
        make_user(role=UserRole.ADMIN)

def test_admin_cannot_self_delete(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.delete(f"/api/users/{admin.id}", headers=auth_headers(admin))
    assert resp.status_code == 400

def test_admin_can_delete_other_user(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    target, _ = make_user(role=UserRole.USER)
    resp = client.delete(f"/api/users/{target.id}", headers=auth_headers(admin))
    assert resp.status_code == 204