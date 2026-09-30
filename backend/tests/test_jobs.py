import uuid

from app.models.job import Job, JobExtractionStatus
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

    Second fix: the original assertion also asserted a specific order
    (["Job by r1", "Job by r2"]), which is flaky — list_jobs orders by
    Job.created_at.desc() alone with no tiebreaker, and two jobs created
    back-to-back in a test can land on the same timestamp. Asserting
    membership (a set) instead of order is the only thing the endpoint
    actually guarantees.
    """
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    client.post("/api/jobs", json={"title": "Job by r1"}, headers=auth_headers(r1))
    client.post("/api/jobs", json={"title": "Job by r2"}, headers=auth_headers(r2))
    titles = {j["title"] for j in client.get("/api/jobs", headers=auth_headers(r1)).json()}
    assert titles == {"Job by r1", "Job by r2"}

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

def test_jd_upload_pdf_populates_raw_text(client, make_user, auth_headers, pdf_bytes):
    """
    Rewrite note: the original version of this test uploaded a .txt file
    with content_type "text/plain" and expected 200. That's not reachable
    in practice — upload_jd's _ALLOWED_JD_CONTENT_TYPES gate (pdf/docx
    only) runs before extract_text_from_upload's extension check, so a
    text/plain upload is always rejected with 415 regardless of filename.
    See test_jd_upload_txt_blocked_by_content_type_gate below, which
    documents that gap directly. This test exercises the actual reachable
    success path instead: a real PDF.
    """
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()["id"]
    files = {"file": ("jd.pdf", pdf_bytes("We need a senior backend engineer."), "application/pdf")}
    resp = client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 200
    assert "senior backend engineer" in resp.json()["jd_raw_text"]

def test_jd_upload_txt_blocked_by_content_type_gate(client, make_user, auth_headers):
    """
    core/text_extract.py's ALLOWED_EXTENSIONS includes .txt, but
    routes/jobs.py's upload_jd checks content_type against
    _ALLOWED_JD_CONTENT_TYPES (pdf/docx only) first — so .txt support in
    the extractor is currently dead code, unreachable through this route.
    Documenting actual behavior; flag to the team if .txt should really be
    accepted here, since that'd be a product decision, not a test fix.
    """
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()["id"]
    files = {"file": ("jd.txt", b"We need a senior backend engineer.", "text/plain")}
    resp = client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 415

def test_jd_upload_rejects_bad_content_type(client, make_user, auth_headers):
    """
    Rewrite note: originally asserted 400 for a bad extension/content-type
    combo. The actual check order is content-type first (415), and the
    route never gets far enough to evaluate the extension at all.
    """
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()["id"]

    files = {"file": ("jd.exe", b"not a jd", "application/octet-stream")}
    resp = client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 415

def test_jd_upload_others_job_forbidden(client, make_user, auth_headers):
    """Another write-isolation case with no prior coverage: JD upload also
    goes through _get_owned_job."""
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(r1)).json()["id"]
    files = {"file": ("jd.txt", b"text", "text/plain")}
    resp = client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(r2))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/jobs/{id} — status transitions (no prior coverage at all)
# ---------------------------------------------------------------------------

def _make_publishable_job(client, auth_headers, recruiter, pdf_bytes, title="Job", description="Do the work"):
    job_id = client.post(
        "/api/jobs", json={"title": title, "description": description}, headers=auth_headers(recruiter),
    ).json()["id"]
    files = {"file": ("jd.pdf", pdf_bytes("JD text"), "application/pdf")}
    client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(recruiter))
    return job_id

def test_publish_requires_title_and_description(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()["id"]
    files = {"file": ("jd.pdf", pdf_bytes("JD text"), "application/pdf")}
    client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(recruiter))
    # no description was ever set
    resp = client.patch(f"/api/jobs/{job_id}", json={"status": "published"}, headers=auth_headers(recruiter))
    assert resp.status_code == 400

def test_publish_requires_jd_upload(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post(
        "/api/jobs", json={"title": "Job", "description": "Do the work"}, headers=auth_headers(recruiter),
    ).json()["id"]
    resp = client.patch(f"/api/jobs/{job_id}", json={"status": "published"}, headers=auth_headers(recruiter))
    assert resp.status_code == 400

def test_publish_succeeds_with_title_description_and_jd(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _make_publishable_job(client, auth_headers, recruiter, pdf_bytes)
    resp = client.patch(f"/api/jobs/{job_id}", json={"status": "published"}, headers=auth_headers(recruiter))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "published"
    assert body["published_at"] is not None

def test_closed_job_cannot_transition_further(client, make_user, auth_headers, pdf_bytes):
    """CLOSED has an empty allowed-transitions set — it's terminal."""
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _make_publishable_job(client, auth_headers, recruiter, pdf_bytes)
    client.patch(f"/api/jobs/{job_id}", json={"status": "published"}, headers=auth_headers(recruiter))
    client.patch(f"/api/jobs/{job_id}", json={"status": "closed"}, headers=auth_headers(recruiter))
    resp = client.patch(f"/api/jobs/{job_id}", json={"status": "published"}, headers=auth_headers(recruiter))
    assert resp.status_code == 400

def test_draft_can_go_straight_to_closed(client, make_user, auth_headers):
    """DRAFT's allowed set includes CLOSED directly, skipping PUBLISHED —
    and unlike publishing, closing has no title/description/JD prerequisite."""
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()["id"]
    resp = client.patch(f"/api/jobs/{job_id}", json={"status": "closed"}, headers=auth_headers(recruiter))
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


# ---------------------------------------------------------------------------
# GET /api/jobs — candidate visibility and filters (no prior coverage)
# ---------------------------------------------------------------------------

def test_candidate_only_sees_published_jobs(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    published_id = _make_publishable_job(client, auth_headers, recruiter, pdf_bytes, title="Published job")
    client.patch(f"/api/jobs/{published_id}", json={"status": "published"}, headers=auth_headers(recruiter))
    client.post("/api/jobs", json={"title": "Still a draft"}, headers=auth_headers(recruiter))

    titles = {j["title"] for j in client.get("/api/jobs", headers=auth_headers(candidate)).json()}
    assert titles == {"Published job"}

def test_candidate_cannot_view_unpublished_job_by_id(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = client.post("/api/jobs", json={"title": "Draft job"}, headers=auth_headers(recruiter)).json()["id"]
    resp = client.get(f"/api/jobs/{job_id}", headers=auth_headers(candidate))
    assert resp.status_code == 404

def test_location_filter_is_case_insensitive_substring(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    client.post("/api/jobs", json={"title": "A", "location": "San Francisco, CA"}, headers=auth_headers(recruiter))
    client.post("/api/jobs", json={"title": "B", "location": "Austin, TX"}, headers=auth_headers(recruiter))
    resp = client.get("/api/jobs?location=francisco", headers=auth_headers(recruiter))
    titles = [j["title"] for j in resp.json()]
    assert titles == ["A"]

def test_employment_type_filter(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    client.post("/api/jobs", json={"title": "FT", "employment_type": "full_time"}, headers=auth_headers(recruiter))
    client.post("/api/jobs", json={"title": "PT", "employment_type": "part_time"}, headers=auth_headers(recruiter))
    resp = client.get("/api/jobs?employment_type=part_time", headers=auth_headers(recruiter))
    titles = [j["title"] for j in resp.json()]
    assert titles == ["PT"]

def test_unauthenticated_request_rejected(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# JD extraction dispatch — happens at JD upload time, nowhere else
# ---------------------------------------------------------------------------

def test_jd_upload_queues_skills_extraction(client, make_user, auth_headers, pdf_bytes, dispatched):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()["id"]
    assert dispatched["jd"] == []  # creating a job does not extract anything
    files = {"file": ("jd.pdf", pdf_bytes("We need a backend engineer."), "application/pdf")}
    resp = client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 200
    assert dispatched["jd"] == [job_id]
    assert resp.json()["skills_extraction_status"] == "pending"

def test_rejected_jd_upload_queues_nothing(client, make_user, auth_headers, dispatched):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()["id"]
    files = {"file": ("jd.txt", b"text", "text/plain")}
    resp = client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 415
    assert dispatched["jd"] == []

def test_jd_reupload_clears_previous_skills_and_requeues(client, make_user, auth_headers, pdf_bytes, dispatched, db):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    headers = auth_headers(recruiter)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=headers).json()["id"]
    files = {"file": ("jd.pdf", pdf_bytes("v1"), "application/pdf")}
    client.post(f"/api/jobs/{job_id}/jd", files=files, headers=headers)

    # Simulate the worker finishing the first extraction.
    job = db.get(Job, uuid.UUID(job_id))
    job.skills_result = ["python"]
    job.skills_extraction_status = JobExtractionStatus.DONE
    db.commit()
    body = client.get(f"/api/jobs/{job_id}", headers=headers).json()
    assert body["skills_result"] == ["python"]
    assert body["skills_extraction_status"] == "done"

    files = {"file": ("jd2.pdf", pdf_bytes("v2"), "application/pdf")}
    resp = client.post(f"/api/jobs/{job_id}/jd", files=files, headers=headers)
    assert resp.json()["skills_result"] is None
    assert resp.json()["skills_extraction_status"] == "pending"
    assert dispatched["jd"] == [job_id, job_id]


# ---------------------------------------------------------------------------
# JD skills extraction results: persisted on the row AND visible via the API
# ---------------------------------------------------------------------------

def test_new_job_exposes_jd_skills_fields_with_defaults(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    body = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()
    assert body["skills_result"] is None
    assert body["skills_section_heading"] is None
    assert body["skills_extraction_status"] == "pending"
    assert body["skills_extraction_error"] is None
    assert body["skills_extracted_at"] is None
    assert body["min_experience_months"] is None

def test_finished_jd_extraction_is_readable_via_get(client, make_user, auth_headers, db):
    """What the worker writes (see jd_skills_extraction_tasks.py) comes
    back through GET /jobs/{id}, the same way ResumeRead exposes a resume's."""
    from datetime import datetime, timezone

    recruiter, _ = make_user(role=UserRole.RECRUITER)
    headers = auth_headers(recruiter)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=headers).json()["id"]

    job = db.get(Job, uuid.UUID(job_id))
    job.skills_result = ["python", "fastapi", "aws ecs"]
    job.skills_section_heading = "Required Skills"
    job.skills_extraction_status = JobExtractionStatus.DONE
    job.skills_extracted_at = datetime.now(timezone.utc)
    job.min_experience_months = 36
    db.commit()

    body = client.get(f"/api/jobs/{job_id}", headers=headers).json()
    assert body["skills_result"] == ["python", "fastapi", "aws ecs"]
    assert body["skills_section_heading"] == "Required Skills"
    assert body["skills_extraction_status"] == "done"
    assert body["skills_extracted_at"] is not None
    assert body["min_experience_months"] == 36

def test_failed_jd_extraction_error_is_readable(client, make_user, auth_headers, db):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    headers = auth_headers(recruiter)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=headers).json()["id"]

    job = db.get(Job, uuid.UUID(job_id))
    job.skills_extraction_status = JobExtractionStatus.FAILED
    job.skills_extraction_error = "Could not locate a required-skills section in this JD."
    db.commit()

    body = client.get(f"/api/jobs/{job_id}", headers=headers).json()
    assert body["skills_extraction_status"] == "failed"
    assert "required-skills section" in body["skills_extraction_error"]


# ---------------------------------------------------------------------------
# POST /jobs/{id}/extract-skills -- manual re-run
# ---------------------------------------------------------------------------

def test_extract_skills_requeues_and_resets_failure_state(client, make_user, auth_headers, pdf_bytes, dispatched, db):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    headers = auth_headers(recruiter)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=headers).json()["id"]
    files = {"file": ("jd.pdf", pdf_bytes("We need a backend engineer."), "application/pdf")}
    client.post(f"/api/jobs/{job_id}/jd", files=files, headers=headers)
    assert dispatched["jd"] == [job_id]

    # Simulate a row the retry sweep has given up on.
    job = db.get(Job, uuid.UUID(job_id))
    job.skills_extraction_status = JobExtractionStatus.FAILED
    job.skills_extraction_error = "boom"
    job.skills_extraction_retry_count = 3
    db.commit()

    resp = client.post(f"/api/jobs/{job_id}/extract-skills", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["skills_extraction_status"] == "pending"
    assert resp.json()["skills_extraction_error"] is None
    assert dispatched["jd"] == [job_id, job_id]

    db.expire_all()
    assert db.get(Job, uuid.UUID(job_id)).skills_extraction_retry_count == 0

def test_extract_skills_without_a_jd_is_rejected(client, make_user, auth_headers, dispatched):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    headers = auth_headers(recruiter)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=headers).json()["id"]
    resp = client.post(f"/api/jobs/{job_id}/extract-skills", headers=headers)
    assert resp.status_code == 400
    assert dispatched["jd"] == []

def test_extract_skills_on_others_job_is_404(client, make_user, auth_headers, pdf_bytes, dispatched):
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(r1)).json()["id"]
    files = {"file": ("jd.pdf", pdf_bytes("We need a backend engineer."), "application/pdf")}
    client.post(f"/api/jobs/{job_id}/jd", files=files, headers=auth_headers(r1))
    resp = client.post(f"/api/jobs/{job_id}/extract-skills", headers=auth_headers(r2))
    assert resp.status_code == 404
    assert dispatched["jd"] == [job_id]  # only the original upload

def test_candidate_cannot_trigger_extract_skills(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = client.post("/api/jobs", json={"title": "Job"}, headers=auth_headers(recruiter)).json()["id"]
    resp = client.post(f"/api/jobs/{job_id}/extract-skills", headers=auth_headers(candidate))
    assert resp.status_code == 403