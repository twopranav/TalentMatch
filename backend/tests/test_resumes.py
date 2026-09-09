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
    assert body["status"] == "uploaded"

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

def test_recruiter_sees_every_resume(client, make_user, auth_headers, pdf_bytes):
    c1, _ = make_user(role=UserRole.USER)
    c2, _ = make_user(role=UserRole.USER)
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    client.post("/api/resumes", files={"file": ("c1.pdf", pdf_bytes("c1"), "application/pdf")}, headers=auth_headers(c1))
    client.post("/api/resumes", files={"file": ("c2.pdf", pdf_bytes("c2"), "application/pdf")}, headers=auth_headers(c2))
    listing = client.get("/api/resumes", headers=auth_headers(recruiter)).json()
    assert len(listing) == 2

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

def test_recruiter_can_view_any_resume(client, make_user, auth_headers, pdf_bytes):
    owner, _ = make_user(role=UserRole.USER)
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    resume_id = client.post(
        "/api/resumes", files={"file": ("resume.pdf", pdf_bytes("r"), "application/pdf")}, headers=auth_headers(owner),
    ).json()["id"]
    resp = client.get(f"/api/resumes/{resume_id}", headers=auth_headers(recruiter))
    assert resp.status_code == 200

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