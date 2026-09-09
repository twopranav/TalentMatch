from app.models.user import UserRole

# ---------------------------------------------------------------------------
# GET/PATCH /api/users/me
# ---------------------------------------------------------------------------

def test_get_me_returns_own_profile(client, make_user, auth_headers):
    user, _ = make_user(email="whoami@test.com")
    resp = client.get("/api/users/me", headers=auth_headers(user))
    assert resp.status_code == 200
    assert resp.json()["email"] == "whoami@test.com"

def test_get_me_requires_auth(client):
    resp = client.get("/api/users/me")
    assert resp.status_code == 401

def test_update_me_edits_profile_fields(client, make_user, auth_headers):
    user, _ = make_user(role=UserRole.USER)
    resp = client.patch(
        "/api/users/me",
        json={"full_name": "Ada Lovelace", "skills": ["python", "sql"], "experience_years": 5},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "Ada Lovelace"
    assert body["skills"] == ["python", "sql"]
    assert body["experience_years"] == 5

def test_update_me_cannot_change_role(client, make_user, auth_headers):
    """UserProfileUpdate deliberately excludes role/is_active/email/password
    (see the route's own docstring) — sending 'role' in the body is just an
    unknown field Pydantic ignores, not a privilege-escalation path."""
    user, _ = make_user(role=UserRole.USER)
    resp = client.patch(
        "/api/users/me",
        json={"full_name": "Still Just A User", "role": "admin"},
        headers=auth_headers(user),
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == UserRole.USER.value

def test_update_me_requires_auth(client):
    resp = client.patch("/api/users/me", json={"full_name": "Nobody"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/users/me/avatar
# ---------------------------------------------------------------------------

def test_avatar_upload_and_download_roundtrip(client, make_user, auth_headers):
    user, _ = make_user()
    files = {"file": ("me.png", b"\x89PNG\r\n\x1a\nfakepngbytes", "image/png")}
    resp = client.post("/api/users/me/avatar", files=files, headers=auth_headers(user))
    assert resp.status_code == 200
    avatar_url = resp.json()["avatar_url"]
    assert avatar_url == f"/api/users/{user.id}/avatar/file"

    file_resp = client.get(avatar_url)
    assert file_resp.status_code == 200
    assert file_resp.content == b"\x89PNG\r\n\x1a\nfakepngbytes"

def test_avatar_upload_rejects_bad_content_type(client, make_user, auth_headers):
    user, _ = make_user()
    files = {"file": ("me.gif", b"GIF89a", "image/gif")}
    resp = client.post("/api/users/me/avatar", files=files, headers=auth_headers(user))
    assert resp.status_code == 415

def test_avatar_upload_rejects_oversized_file(client, make_user, auth_headers):
    user, _ = make_user()
    oversized = b"0" * (5 * 1024 * 1024 + 1)
    files = {"file": ("big.png", oversized, "image/png")}
    resp = client.post("/api/users/me/avatar", files=files, headers=auth_headers(user))
    assert resp.status_code == 413

def test_avatar_replace_removes_old_blob(client, make_user, auth_headers):
    """A second upload replaces the first rather than accumulating — the
    download still returns the newest bytes."""
    user, _ = make_user()
    headers = auth_headers(user)
    client.post("/api/users/me/avatar", files={"file": ("first.png", b"first-bytes", "image/png")}, headers=headers)
    client.post("/api/users/me/avatar", files={"file": ("second.png", b"second-bytes", "image/png")}, headers=headers)
    avatar_url = client.get("/api/users/me", headers=headers).json()["avatar_url"]
    file_resp = client.get(avatar_url)
    assert file_resp.content == b"second-bytes"

def test_get_avatar_file_404_when_none_set(client, make_user):
    user, _ = make_user()
    resp = client.get(f"/api/users/{user.id}/avatar/file")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/users/{id} — blocked while the target still owns jobs
# ---------------------------------------------------------------------------

def test_cannot_delete_recruiter_who_owns_jobs(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    client.post("/api/jobs", json={"title": "Owned job"}, headers=auth_headers(recruiter))
    resp = client.delete(f"/api/users/{recruiter.id}", headers=auth_headers(admin))
    assert resp.status_code == 400

def test_can_delete_recruiter_after_jobs_removed(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Owned job"}, headers=auth_headers(recruiter)).json()["id"]
    client.delete(f"/api/jobs/{job_id}", headers=auth_headers(recruiter))
    resp = client.delete(f"/api/users/{recruiter.id}", headers=auth_headers(admin))
    assert resp.status_code == 204