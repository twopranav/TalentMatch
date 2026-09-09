from app.models.user import UserRole


def _published_job(client, auth_headers, recruiter, pdf_bytes, title="Job"):
    job_id = client.post(
        "/api/jobs", json={"title": title, "description": "Do the work"},
        headers=auth_headers(recruiter),
    ).json()["id"]
    files = {"file": ("jd.pdf", pdf_bytes("JD text"), "application/pdf")}
    client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(recruiter))
    client.patch(f"/api/jobs/{job_id}", json={"status": "published"}, headers=auth_headers(recruiter))
    return job_id


def _upload_resume(client, auth_headers, candidate, pdf_bytes):
    files = {"file": ("resume.pdf", pdf_bytes("My resume"), "application/pdf")}
    client.post("/api/resumes", files=files, headers=auth_headers(candidate))


# ---------------------------------------------------------------------------
# POST /api/applications
# ---------------------------------------------------------------------------

def test_apply_succeeds_with_resume_on_published_job(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)

    resp = client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate))
    assert resp.status_code == 201
    body = resp.json()
    assert body["user_id"] == str(candidate.id)
    assert body["job_id"] == job_id
    assert body["status"] == "applied"
    assert body["resume_id"] is not None

def test_apply_without_resume_rejected(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)

    resp = client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate))
    assert resp.status_code == 400

def test_apply_to_unpublished_job_rejected(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = client.post("/api/jobs", json={"title": "Draft job"}, headers=auth_headers(recruiter)).json()["id"]
    _upload_resume(client, auth_headers, candidate, pdf_bytes)

    resp = client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate))
    assert resp.status_code == 404

def test_apply_to_nonexistent_job_rejected(client, make_user, auth_headers, pdf_bytes):
    import uuid
    candidate, _ = make_user(role=UserRole.USER)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)

    resp = client.post(
        "/api/applications", json={"job_id": str(uuid.uuid4()), "resume_id": None}, headers=auth_headers(candidate),
    )
    assert resp.status_code == 404

def test_duplicate_application_rejected(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)

    client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate))
    resp = client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate))
    assert resp.status_code == 400

def test_apply_requires_auth(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    resp = client.post("/api/applications", json={"job_id": job_id, "resume_id": None})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/applications/me
# ---------------------------------------------------------------------------

def test_list_my_applications_includes_job_context(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes, title="My dream job")
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate))

    resp = client.get("/api/applications/me", headers=auth_headers(candidate))
    assert resp.status_code == 200
    [app] = resp.json()
    assert app["job_title"] == "My dream job"
    assert app["job_status"] == "published"

def test_list_my_applications_empty_when_none(client, make_user, auth_headers):
    candidate, _ = make_user(role=UserRole.USER)
    resp = client.get("/api/applications/me", headers=auth_headers(candidate))
    assert resp.status_code == 200
    assert resp.json() == []

def test_list_my_applications_only_shows_own(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate1, _ = make_user(role=UserRole.USER)
    candidate2, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate1, pdf_bytes)
    client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate1))

    resp = client.get("/api/applications/me", headers=auth_headers(candidate2))
    assert resp.json() == []

def test_list_my_applications_requires_auth(client):
    resp = client.get("/api/applications/me")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/applications/job/{job_id}
# ---------------------------------------------------------------------------

def test_owning_recruiter_lists_job_applicants(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate))

    resp = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(recruiter))
    assert resp.status_code == 200
    [applicant] = resp.json()
    assert applicant["applicant_email"] == candidate.email
    assert applicant["resume_filename"] == "resume.pdf"

def test_non_owning_recruiter_forbidden_from_job_applicants(client, make_user, auth_headers, pdf_bytes):
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, r1, pdf_bytes)
    resp = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(r2))
    assert resp.status_code == 403

def test_admin_can_list_any_job_applicants(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    admin, _ = make_user(role=UserRole.ADMIN)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    resp = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(admin))
    assert resp.status_code == 200

def test_candidate_forbidden_from_job_applicants(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    resp = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(candidate))
    assert resp.status_code == 403

def test_job_applicants_404_for_missing_job(client, make_user, auth_headers):
    import uuid
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    resp = client.get(f"/api/applications/job/{uuid.uuid4()}", headers=auth_headers(recruiter))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/applications/{id}/status
# ---------------------------------------------------------------------------

def test_owning_recruiter_updates_status(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    app_id = client.post(
        "/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate),
    ).json()["id"]

    resp = client.patch(
        f"/api/applications/{app_id}/status", json={"status": "shortlisted"}, headers=auth_headers(recruiter),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "shortlisted"

def test_non_owning_recruiter_cannot_update_status(client, make_user, auth_headers, pdf_bytes):
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, r1, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    app_id = client.post(
        "/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate),
    ).json()["id"]

    resp = client.patch(
        f"/api/applications/{app_id}/status", json={"status": "rejected"}, headers=auth_headers(r2),
    )
    assert resp.status_code == 403

def test_candidate_cannot_update_status(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    app_id = client.post(
        "/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate),
    ).json()["id"]

    resp = client.patch(
        f"/api/applications/{app_id}/status", json={"status": "hired"}, headers=auth_headers(candidate),
    )
    assert resp.status_code == 403

def test_update_status_404_for_missing_application(client, make_user, auth_headers):
    import uuid
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    resp = client.patch(
        f"/api/applications/{uuid.uuid4()}/status", json={"status": "hired"}, headers=auth_headers(recruiter),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/applications/{id}
# ---------------------------------------------------------------------------

def test_owner_can_withdraw_application(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    app_id = client.post(
        "/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate),
    ).json()["id"]

    resp = client.delete(f"/api/applications/{app_id}", headers=auth_headers(candidate))
    assert resp.status_code == 204
    assert client.get("/api/applications/me", headers=auth_headers(candidate)).json() == []

def test_other_user_cannot_withdraw_application(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    other, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    app_id = client.post(
        "/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate),
    ).json()["id"]

    resp = client.delete(f"/api/applications/{app_id}", headers=auth_headers(other))
    assert resp.status_code == 404

def test_withdraw_404_for_missing_application(client, make_user, auth_headers):
    import uuid
    candidate, _ = make_user(role=UserRole.USER)
    resp = client.delete(f"/api/applications/{uuid.uuid4()}", headers=auth_headers(candidate))
    assert resp.status_code == 404

def test_withdraw_requires_auth(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    app_id = client.post(
        "/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate),
    ).json()["id"]

    resp = client.delete(f"/api/applications/{app_id}")
    assert resp.status_code == 401