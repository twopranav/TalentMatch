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

def test_recruiter_sees_only_own_jobs(client, make_user, auth_headers):
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    client.post("/api/jobs", json={"title": "Job by r1"}, headers=auth_headers(r1))
    client.post("/api/jobs", json={"title": "Job by r2"}, headers=auth_headers(r2))
    titles = [j["title"] for j in client.get("/api/jobs", headers=auth_headers(r1)).json()]
    assert titles == ["Job by r1"]

def test_admin_sees_all_jobs(client, make_user, auth_headers):
    r1, _ = make_user(role=UserRole.RECRUITER)
    admin, _ = make_user(role=UserRole.ADMIN)
    client.post("/api/jobs", json={"title": "Job by r1"}, headers=auth_headers(r1))
    titles = [j["title"] for j in client.get("/api/jobs", headers=auth_headers(admin)).json()]
    assert "Job by r1" in titles

def test_recruiter_cannot_access_others_job(client, make_user, auth_headers):
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Private"}, headers=auth_headers(r1)).json()["id"]
    resp = client.get(f"/api/jobs/{job_id}", headers=auth_headers(r2))
    assert resp.status_code == 404  # deliberately 404 not 403 — see _get_owned_job's comment

def test_admin_can_access_any_job(client, make_user, auth_headers):
    r1, _ = make_user(role=UserRole.RECRUITER)
    admin, _ = make_user(role=UserRole.ADMIN)
    job_id = client.post("/api/jobs", json={"title": "Some job"}, headers=auth_headers(r1)).json()["id"]
    resp = client.get(f"/api/jobs/{job_id}", headers=auth_headers(admin))
    assert resp.status_code == 200

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