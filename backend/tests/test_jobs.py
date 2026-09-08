from app.models.user import UserRole

def test_user_role_cannot_create_job(client, make_user, auth_headers):
    user, _ = make_user(role=UserRole.USER)
    resp = client.post("/api/jobs", json={"title": "Backend Engineer"}, headers=auth_headers(user))
    assert resp.status_code == 403

def test_recruiter_creates_and_owns_job(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    resp = client.post("/api/jobs", json={"title": "Backend Engineer"}, headers=auth_headers(recruiter))
    assert resp.status_code == 201
    assert resp.json()["created_by_id"] == str(recruiter.id)

def test_recruiter_sees_all_jobs(client, make_user, auth_headers):
    """
    Rewrite note: this used to assert recruiters only see their own jobs.
    That's not the actual design — _get_visible_job's own docstring states
    recruiters get "full view, no ownership restriction" on reads.
    Ownership only gates writes (see test_recruiter_cannot_update_others_job
    below). Confirmed as intended product behavior, not a bug, before
    changing this test.
    """
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    client.post("/api/jobs", json={"title": "Job by r1"}, headers=auth_headers(r1))
    client.post("/api/jobs", json={"title": "Job by r2"}, headers=auth_headers(r2))
    titles = [j["title"] for j in client.get("/api/jobs", headers=auth_headers(r1)).json()]
    assert titles == ["Job by r1", "Job by r2"]

def test_admin_sees_all_jobs(client, make_user, auth_headers):
    r1, _ = make_user(role=UserRole.RECRUITER)
    admin, _ = make_user(role=UserRole.ADMIN)
    client.post("/api/jobs", json={"title": "Job by r1"}, headers=auth_headers(r1))
    titles = [j["title"] for j in client.get("/api/jobs", headers=auth_headers(admin)).json()]
    assert "Job by r1" in titles

def test_recruiter_can_view_others_job(client, make_user, auth_headers):
    """Rewrite of the old test_recruiter_cannot_access_others_job — reading
    another recruiter's job is allowed (shared visibility); only editing it
    isn't (see test_recruiter_cannot_update_others_job)."""
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Some job"}, headers=auth_headers(r1)).json()["id"]
    resp = client.get(f"/api/jobs/{job_id}", headers=auth_headers(r2))
    assert resp.status_code == 200

def test_recruiter_cannot_update_others_job(client, make_user, auth_headers):
    """This is the actual isolation rule the codebase enforces —
    _get_owned_job restricts writes to the owning recruiter (or an
    admin/superuser), unlike reads. Had zero test coverage before this."""
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Private"}, headers=auth_headers(r1)).json()["id"]
    resp = client.patch(
        f"/api/jobs/{job_id}",
        json={"title": "Hijacked"},
        headers=auth_headers(r2),
    )
    assert resp.status_code == 404  # 404 not 403 — see _get_owned_job's comment on avoiding existence leaks

def test_recruiter_cannot_delete_others_job(client, make_user, auth_headers):
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Private"}, headers=auth_headers(r1)).json()["id"]
    resp = client.delete(f"/api/jobs/{job_id}", headers=auth_headers(r2))
    assert resp.status_code == 404

def test_admin_can_access_any_job(client, make_user, auth_headers):
    r1, _ = make_user(role=UserRole.RECRUITER)
    admin, _ = make_user(role=UserRole.ADMIN)
    job_id = client.post("/api/jobs", json={"title": "Some job"}, headers=auth_headers(r1)).json()["id"]
    resp = client.get(f"/api/jobs/{job_id}", headers=auth_headers(admin))
    assert resp.status_code == 200

def test_admin_can_update_others_job(client, make_user, auth_headers):
    """Coverage gap fill: admins are the "privileged" branch in
    _get_owned_job, meaning they should be able to edit any recruiter's
    job, not just view it. Wasn't tested before."""
    r1, _ = make_user(role=UserRole.RECRUITER)
    admin, _ = make_user(role=UserRole.ADMIN)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(r1)).json()["id"]
    resp = client.patch(
        f"/api/jobs/{job_id}",
        json={"title": "Edited by admin"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Edited by admin"

def test_jd_upload_txt_populates_raw_text(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()["id"]
    files = {"file": ("jd.txt", b"We need a senior backend engineer.", "text/plain")}
    resp = client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 200
    assert "senior backend engineer" in resp.json()["jd_raw_text"]

def test_jd_upload_rejects_bad_extension(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()["id"]

    files = {"file": ("jd.exe", b"not a jd", "application/octet-stream")}
    resp = client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 400

def test_jd_upload_others_job_forbidden(client, make_user, auth_headers):
    """Another write-isolation case with no prior coverage: JD upload also
    goes through _get_owned_job."""
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(r1)).json()["id"]
    files = {"file": ("jd.txt", b"text", "text/plain")}
    resp = client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(r2))
    assert resp.status_code == 404