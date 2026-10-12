from app.models.user import UserRole

# ---------------------------------------------------------------------------
# POST /api/resumes — self-upload
# ---------------------------------------------------------------------------

def test_self_upload_becomes_owner(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    files = {"file": ("resume.pdf", pdf_bytes("My resume"), "application/pdf")}
    resp = client.post("/api/resumes", files=files, headers=auth_headers(candidate))
    assert resp.status_code == 201
    body = resp.json()
    assert body["owner_id"] == str(candidate.id)
    assert body["uploaded_by_id"] == str(candidate.id)
    assert body["status"] == "UPLOADED"

def test_upload_rejects_bad_content_type(client, make_user, auth_headers):
    candidate, _ = make_user(role=UserRole.USER)
    files = {"file": ("resume.txt", b"not allowed", "text/plain")}
    resp = client.post("/api/resumes", files=files, headers=auth_headers(candidate))
    assert resp.status_code == 415

def test_upload_rejects_oversized_file(client, make_user, auth_headers):
    candidate, _ = make_user(role=UserRole.USER)
    oversized = b"0" * (10 * 1024 * 1024 + 1)
    files = {"file": ("resume.pdf", oversized, "application/pdf")}
    resp = client.post("/api/resumes", files=files, headers=auth_headers(candidate))
    assert resp.status_code == 413

def test_second_self_upload_replaces_first(client, make_user, auth_headers, pdf_bytes):
    """A candidate has at most one active resume — a repeat upload replaces
    the old one rather than accumulating (see upload_resume's docstring)."""
    candidate, _ = make_user(role=UserRole.USER)
    headers = auth_headers(candidate)
    client.post("/api/resumes", files={"file": ("first.pdf", pdf_bytes("v1"), "application/pdf")}, headers=headers)
    client.post("/api/resumes", files={"file": ("second.pdf", pdf_bytes("v2"), "application/pdf")}, headers=headers)
    listing = client.get("/api/resumes", headers=headers).json()
    assert len(listing) == 1
    assert listing[0]["original_filename"] == "second.pdf"

def test_docx_upload_accepted(client, make_user, auth_headers, docx_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    files = {
        "file": (
            "resume.docx",
            docx_bytes("My resume"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    resp = client.post("/api/resumes", files=files, headers=auth_headers(candidate))
    assert resp.status_code == 201


# ---------------------------------------------------------------------------
# POST /api/resumes/bulk — recruiter/admin sourcing upload
# ---------------------------------------------------------------------------

def test_bulk_upload_requires_recruiter_or_admin(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    files = [("files", ("a.pdf", pdf_bytes("a"), "application/pdf"))]
    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(candidate))
    assert resp.status_code == 403

def test_bulk_upload_owner_id_is_null(client, make_user, auth_headers, pdf_bytes):
    """Sourced resumes have no candidate account yet (see _store_one's
    comment: owner_id stays null, uploaded_by_id is the recruiter)."""
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    files = [("files", ("sourced.pdf", pdf_bytes("sourced"), "application/pdf"))]
    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 200
    [result] = resp.json()
    assert result["success"] is True
    assert result["resume"]["owner_id"] is None
    assert result["resume"]["uploaded_by_id"] == str(recruiter.id)

def test_bulk_upload_partial_failure_does_not_sink_batch(client, make_user, auth_headers, pdf_bytes):
    """One bad file in a batch shouldn't fail the others — each file
    succeeds/fails independently (see upload_resumes_bulk's docstring)."""
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    files = [
        ("files", ("good.pdf", pdf_bytes("good"), "application/pdf")),
        ("files", ("bad.txt", b"nope", "text/plain")),
    ]
    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 200
    results = {r["original_filename"]: r for r in resp.json()}
    assert results["good.pdf"]["success"] is True
    assert results["bad.txt"]["success"] is False
    assert results["bad.txt"]["error"] is not None

    # the failed file must not have left a partial row behind
    listing = client.get("/api/resumes", headers=auth_headers(recruiter)).json()
    assert len(listing) == 1
    assert listing[0]["original_filename"] == "good.pdf"


# ---------------------------------------------------------------------------
# GET /api/resumes — visibility split (own vs everything)
# ---------------------------------------------------------------------------

def test_candidate_sees_only_own_resume(client, make_user, auth_headers, pdf_bytes):
    c1, _ = make_user(role=UserRole.USER)
    c2, _ = make_user(role=UserRole.USER)
    client.post("/api/resumes", files={"file": ("c1.pdf", pdf_bytes("c1"), "application/pdf")}, headers=auth_headers(c1))
    client.post("/api/resumes", files={"file": ("c2.pdf", pdf_bytes("c2"), "application/pdf")}, headers=auth_headers(c2))
    listing = client.get("/api/resumes", headers=auth_headers(c1)).json()
    assert len(listing) == 1
    assert listing[0]["original_filename"] == "c1.pdf"

def _bulk_upload(client, auth_headers, uploader, pdf_bytes, names):
    files = [("files", (n, pdf_bytes(f"Resume {n}"), "application/pdf")) for n in names]
    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(uploader))
    assert resp.status_code == 200
    return {r["original_filename"]: r["resume"]["id"] for r in resp.json() if r["success"]}

def test_recruiter_library_only_shows_own_uploads(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    client.post("/api/resumes", files={"file": ("cand.pdf", pdf_bytes("cand"), "application/pdf")}, headers=auth_headers(candidate))
    _bulk_upload(client, auth_headers, r1, pdf_bytes, ["r1-a.pdf", "r1-b.pdf"])
    _bulk_upload(client, auth_headers, r2, pdf_bytes, ["r2-a.pdf"])

    names1 = sorted(r["original_filename"] for r in client.get("/api/resumes", headers=auth_headers(r1)).json())
    names2 = sorted(r["original_filename"] for r in client.get("/api/resumes", headers=auth_headers(r2)).json())
    assert names1 == ["r1-a.pdf", "r1-b.pdf"]
    assert names2 == ["r2-a.pdf"]

def test_superuser_and_admin_see_every_resume(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    superuser, _ = make_user(role=UserRole.SUPERUSER)
    admin, _ = make_user(role=UserRole.ADMIN)
    client.post("/api/resumes", files={"file": ("cand.pdf", pdf_bytes("cand"), "application/pdf")}, headers=auth_headers(candidate))
    _bulk_upload(client, auth_headers, r1, pdf_bytes, ["r1-a.pdf"])
    _bulk_upload(client, auth_headers, r2, pdf_bytes, ["r2-a.pdf"])
    for viewer in (superuser, admin):
        listing = client.get("/api/resumes", headers=auth_headers(viewer)).json()
        assert len(listing) == 3

def test_recruiter_can_view_own_upload_but_not_unrelated_resumes(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    cand_resume = client.post(
        "/api/resumes", files={"file": ("resume.pdf", pdf_bytes("r"), "application/pdf")}, headers=auth_headers(candidate),
    ).json()["id"]
    mine = _bulk_upload(client, auth_headers, r1, pdf_bytes, ["mine.pdf"])["mine.pdf"]
    theirs = _bulk_upload(client, auth_headers, r2, pdf_bytes, ["theirs.pdf"])["theirs.pdf"]

    assert client.get(f"/api/resumes/{mine}", headers=auth_headers(r1)).status_code == 200
    for rid in (cand_resume, theirs):
        assert client.get(f"/api/resumes/{rid}", headers=auth_headers(r1)).status_code == 404
        assert client.get(f"/api/resumes/{rid}/file", headers=auth_headers(r1)).status_code == 404

def test_recruiter_can_view_resume_of_applicant_to_their_job(client, make_user, auth_headers, pdf_bytes):
    """The applicants page opens each applicant's resume, so a recruiter must
    reach candidate resumes attached to applications on jobs they created
    (and only those)."""
    from conftest import TestSessionLocal
    from app.models.resume import Resume, ResumeExtractionStatus

    candidate, _ = make_user(role=UserRole.USER)
    owner, _ = make_user(role=UserRole.RECRUITER)
    other, _ = make_user(role=UserRole.RECRUITER)
    job_id = client.post(
        "/api/jobs", json={"title": "Job", "description": "Do the work"}, headers=auth_headers(owner),
    ).json()["id"]
    client.post(f"/api/jobs/{job_id}/jd", files={"file": ("jd.pdf", pdf_bytes("JD text"), "application/pdf")}, headers=auth_headers(owner))
    client.patch(f"/api/jobs/{job_id}", json={"status": "published"}, headers=auth_headers(owner))
    resume_id = client.post(
        "/api/resumes", files={"file": ("resume.pdf", pdf_bytes("r"), "application/pdf")}, headers=auth_headers(candidate),
    ).json()["id"]
    session = TestSessionLocal()
    try:
        session.query(Resume).filter(Resume.owner_id == candidate.id).update(
            {"skills_extraction_status": ResumeExtractionStatus.DONE}
        )
        session.commit()
    finally:
        session.close()

    assert client.get(f"/api/resumes/{resume_id}/file", headers=auth_headers(owner)).status_code == 404
    assert client.post("/api/applications", json={"job_id": job_id}, headers=auth_headers(candidate)).status_code == 201
    assert client.get(f"/api/resumes/{resume_id}/file", headers=auth_headers(owner)).status_code == 200
    assert client.get(f"/api/resumes/{resume_id}/file", headers=auth_headers(other)).status_code == 404

def test_superuser_can_view_any_resume(client, make_user, auth_headers, pdf_bytes):
    owner, _ = make_user(role=UserRole.USER)
    superuser, _ = make_user(role=UserRole.SUPERUSER)
    resume_id = client.post(
        "/api/resumes", files={"file": ("resume.pdf", pdf_bytes("r"), "application/pdf")}, headers=auth_headers(owner),
    ).json()["id"]
    assert client.get(f"/api/resumes/{resume_id}", headers=auth_headers(superuser)).status_code == 200

def test_archived_resume_excluded_by_default(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    headers = auth_headers(candidate)
    resume_id = client.post(
        "/api/resumes", files={"file": ("resume.pdf", pdf_bytes("r"), "application/pdf")}, headers=headers,
    ).json()["id"]
    client.patch(f"/api/resumes/{resume_id}/archive?archived=true", headers=headers)
    assert client.get("/api/resumes", headers=headers).json() == []
    included = client.get("/api/resumes?include_archived=true", headers=headers).json()
    assert len(included) == 1


# ---------------------------------------------------------------------------
# GET /api/resumes/{id} and /{id}/file — visibility on a single resume
# ---------------------------------------------------------------------------

def test_owner_can_view_own_resume(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    headers = auth_headers(candidate)
    resume_id = client.post(
        "/api/resumes", files={"file": ("resume.pdf", pdf_bytes("r"), "application/pdf")}, headers=headers,
    ).json()["id"]
    resp = client.get(f"/api/resumes/{resume_id}", headers=headers)
    assert resp.status_code == 200
    assert "download_url" in resp.json()

def test_other_candidate_cannot_view_resume(client, make_user, auth_headers, pdf_bytes):
    owner, _ = make_user(role=UserRole.USER)
    other, _ = make_user(role=UserRole.USER)
    resume_id = client.post(
        "/api/resumes", files={"file": ("resume.pdf", pdf_bytes("r"), "application/pdf")}, headers=auth_headers(owner),
    ).json()["id"]
    resp = client.get(f"/api/resumes/{resume_id}", headers=auth_headers(other))
    assert resp.status_code == 404


def test_download_file_returns_original_bytes(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    headers = auth_headers(candidate)
    content = pdf_bytes("distinctive content")
    resume_id = client.post(
        "/api/resumes", files={"file": ("resume.pdf", content, "application/pdf")}, headers=headers,
    ).json()["id"]
    resp = client.get(f"/api/resumes/{resume_id}/file", headers=headers)
    assert resp.status_code == 200
    assert resp.content == content


# ---------------------------------------------------------------------------
# PATCH /api/resumes/{id}/archive and DELETE — manageable-resume access
# ---------------------------------------------------------------------------

def test_owner_can_archive_own_resume(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    headers = auth_headers(candidate)
    resume_id = client.post(
        "/api/resumes", files={"file": ("resume.pdf", pdf_bytes("r"), "application/pdf")}, headers=headers,
    ).json()["id"]
    resp = client.patch(f"/api/resumes/{resume_id}/archive?archived=true", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_archived"] is True

def test_uninvolved_recruiter_cannot_manage_self_uploaded_resume(client, make_user, auth_headers, pdf_bytes):
    """_get_manageable_resume: a recruiter who did NOT source a given
    self-uploaded resume has no write access to it, even though recruiters
    can freely *view* it."""
    candidate, _ = make_user(role=UserRole.USER)
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    resume_id = client.post(
        "/api/resumes", files={"file": ("resume.pdf", pdf_bytes("r"), "application/pdf")}, headers=auth_headers(candidate),
    ).json()["id"]
    resp = client.delete(f"/api/resumes/{resume_id}", headers=auth_headers(recruiter))
    assert resp.status_code == 404

def test_uploading_recruiter_can_manage_sourced_resume(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    files = [("files", ("sourced.pdf", pdf_bytes("s"), "application/pdf"))]
    resume_id = client.post("/api/resumes/bulk", files=files, headers=auth_headers(recruiter)).json()[0]["resume"]["id"]
    resp = client.delete(f"/api/resumes/{resume_id}", headers=auth_headers(recruiter))
    assert resp.status_code == 204

def test_admin_can_manage_any_resume(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    admin, _ = make_user(role=UserRole.ADMIN)
    resume_id = client.post(
        "/api/resumes", files={"file": ("resume.pdf", pdf_bytes("r"), "application/pdf")}, headers=auth_headers(candidate),
    ).json()["id"]
    resp = client.delete(f"/api/resumes/{resume_id}", headers=auth_headers(admin))
    assert resp.status_code == 204

def test_delete_requires_auth(client):
    import uuid
    resp = client.delete(f"/api/resumes/{uuid.uuid4()}")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Extraction dispatch — upload queues skills extraction, nothing else does
# ---------------------------------------------------------------------------

def test_self_upload_queues_skills_extraction(client, make_user, auth_headers, pdf_bytes, dispatched):
    candidate, _ = make_user(role=UserRole.USER)
    files = {"file": ("resume.pdf", pdf_bytes("My resume"), "application/pdf")}
    resp = client.post("/api/resumes", files=files, headers=auth_headers(candidate))
    assert resp.status_code == 201
    assert dispatched["resume"] == [resp.json()["id"]]
    assert resp.json()["skills_extraction_status"] == "pending"

def test_rejected_upload_queues_nothing(client, make_user, auth_headers, dispatched):
    candidate, _ = make_user(role=UserRole.USER)
    files = {"file": ("resume.txt", b"not allowed", "text/plain")}
    client.post("/api/resumes", files=files, headers=auth_headers(candidate))
    assert dispatched["resume"] == []

def test_replacement_upload_queues_only_the_new_resume(client, make_user, auth_headers, pdf_bytes, dispatched):
    candidate, _ = make_user(role=UserRole.USER)
    headers = auth_headers(candidate)
    first = client.post("/api/resumes", files={"file": ("first.pdf", pdf_bytes("v1"), "application/pdf")}, headers=headers).json()
    second = client.post("/api/resumes", files={"file": ("second.pdf", pdf_bytes("v2"), "application/pdf")}, headers=headers).json()
    assert dispatched["resume"] == [first["id"], second["id"]]

def test_bulk_upload_queues_one_task_per_stored_file(client, make_user, auth_headers, pdf_bytes, dispatched):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    files = [
        ("files", ("a.pdf", pdf_bytes("a"), "application/pdf")),
        ("files", ("bad.txt", b"nope", "text/plain")),
        ("files", ("b.pdf", pdf_bytes("b"), "application/pdf")),
    ]
    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 200
    stored_ids = [r["resume"]["id"] for r in resp.json() if r["success"]]
    assert len(stored_ids) == 2
    assert dispatched["resume"] == stored_ids  # the rejected .txt is not queued

def test_manual_extract_skills_resets_status_and_queues(client, make_user, auth_headers, pdf_bytes, dispatched):
    candidate, _ = make_user(role=UserRole.USER)
    headers = auth_headers(candidate)
    resume_id = client.post("/api/resumes", files={"file": ("r.pdf", pdf_bytes("x"), "application/pdf")}, headers=headers).json()["id"]
    resp = client.post(f"/api/resumes/{resume_id}/extract-skills", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["skills_extraction_status"] == "pending"
    assert dispatched["resume"] == [resume_id, resume_id]  # once on upload, once on manual re-run