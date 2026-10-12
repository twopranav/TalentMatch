from conftest import TestSessionLocal  # tests/ is on sys.path (no __init__.py)

from app.models.resume import Resume, ResumeExtractionStatus
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


def _set_skills_status(owner_id, status):
    """Stands in for the Celery worker, which isn't running in tests."""
    session = TestSessionLocal()
    try:
        session.query(Resume).filter(
            Resume.owner_id == owner_id, Resume.is_archived.is_(False),
        ).update({"skills_extraction_status": status})
        session.commit()
    finally:
        session.close()


def _upload_resume(client, auth_headers, candidate, pdf_bytes, skills_status=ResumeExtractionStatus.DONE):
    """Uploads a resume, then simulates the extraction worker finishing it
    (DONE by default) — applying is gated on skills_extraction_status, and
    upload alone leaves it PENDING."""
    files = {"file": ("resume.pdf", pdf_bytes("My resume"), "application/pdf")}
    client.post("/api/resumes", files=files, headers=auth_headers(candidate))
    _set_skills_status(candidate.id, skills_status)


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

def test_apply_rejected_while_resume_still_processing(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes, skills_status=ResumeExtractionStatus.PENDING)

    resp = client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate))
    assert resp.status_code == 400
    assert "still being processed" in resp.json()["detail"]

def test_apply_rejected_when_resume_extraction_failed(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes, skills_status=ResumeExtractionStatus.FAILED)

    resp = client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate))
    assert resp.status_code == 400
    assert "couldn't read your resume" in resp.json()["detail"]

def test_applying_never_queues_extraction(client, make_user, auth_headers, pdf_bytes, dispatched):
    """Extraction happens at upload time; the apply route only checks the
    result and must not dispatch anything itself."""
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    before = (list(dispatched["resume"]), list(dispatched["jd"]))

    resp = client.post("/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate))
    assert resp.status_code == 201
    assert (dispatched["resume"], dispatched["jd"]) == before

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


# ---------------------------------------------------------------------------
# GET /api/applications/job/{job_id} -- ordering
# ---------------------------------------------------------------------------

def test_job_applicants_sorted_by_score_then_earliest_then_name(client, make_user, auth_headers, pdf_bytes):
    from datetime import datetime, timedelta

    from app.models.application import Application

    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)

    candidates = {}
    for key in ("top", "tie_late", "tie_early", "same_time_b", "same_time_a", "unscored"):
        user, _ = make_user(role=UserRole.USER)
        candidates[key] = user
        _upload_resume(client, auth_headers, user, pdf_bytes)
        assert client.post(
            "/api/applications", json={"job_id": job_id}, headers=auth_headers(user),
        ).status_code == 201

    base = datetime(2026, 1, 1, 12, 0, 0)
    plan = {  # key: (score, applied_at offset in minutes, full_name)
        "top": (90.0, 50, "Zed"),
        "tie_late": (70.0, 30, "Aaron"),
        "tie_early": (70.0, 10, "Zoe"),
        "same_time_b": (60.0, 5, "Bea"),
        "same_time_a": (60.0, 5, "Abe"),
        "unscored": (None, 1, "Cy"),
    }
    session = TestSessionLocal()
    try:
        from app.models.user import User

        for key, (score, minutes, name) in plan.items():
            user = candidates[key]
            session.query(User).filter(User.id == user.id).update({"full_name": name})
            session.query(Application).filter(Application.user_id == user.id).update(
                {"match_score": score, "applied_at": base + timedelta(minutes=minutes)}
            )
        session.commit()
    finally:
        session.close()

    resp = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(recruiter))
    assert resp.status_code == 200
    assert [a["applicant_name"] for a in resp.json()] == [
        "Zed", "Zoe", "Aaron", "Abe", "Bea", "Cy",
    ]


def _apply_library_and_set_scores(client, make_user, auth_headers, pdf_bytes, plan, upload_order):
    """Bulk-applies library resumes (no accounts) and pins score / applied_at
    directly in the DB, standing in for the scoring worker. plan is
    {filename: (score, minutes_after_base)}. Returns (job_id, recruiter)."""
    from datetime import datetime, timedelta

    from app.models.application import Application

    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    ids = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, upload_order)
    results = client.post(
        f"/api/applications/job/{job_id}/bulk", json={"resume_ids": list(ids.values())},
        headers=auth_headers(recruiter),
    ).json()
    assert all(r["success"] for r in results)

    base = datetime(2026, 1, 1, 12, 0, 0)
    session = TestSessionLocal()
    try:
        for filename, (score, minutes) in plan.items():
            session.query(Application).filter(Application.resume_id == ids[filename]).update(
                {"match_score": score, "applied_at": base + timedelta(minutes=minutes)}
            )
        session.commit()
    finally:
        session.close()
    return job_id, recruiter


_LIBRARY_SORT_PLAN = {  # filename: (score, minutes after base)
    "zed.pdf": (90.0, 50),
    "bob.pdf": (70.0, 30),   # ties with amy on score, applied later
    "amy.pdf": (70.0, 10),
    "dan.pdf": (60.0, 5),    # ties with cat on score AND time -> name A-Z
    "cat.pdf": (60.0, 5),
    "none.pdf": (None, 1),   # unscored always last, even though applied first
}


def test_library_applicants_sorted_by_score_then_earliest_then_name(client, make_user, auth_headers, pdf_bytes):
    job_id, recruiter = _apply_library_and_set_scores(
        client, make_user, auth_headers, pdf_bytes, _LIBRARY_SORT_PLAN,
        upload_order=["dan.pdf", "none.pdf", "bob.pdf", "zed.pdf", "cat.pdf", "amy.pdf"],
    )
    rows = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(recruiter)).json()
    assert [r["applicant_name"] for r in rows] == [
        "zed.pdf", "amy.pdf", "bob.pdf", "cat.pdf", "dan.pdf", "none.pdf",
    ]
    assert [r["match_score"] for r in rows] == [90.0, 70.0, 70.0, 60.0, 60.0, None]


def test_library_applicants_sort_by_applied_at_is_newest_first(client, make_user, auth_headers, pdf_bytes):
    job_id, recruiter = _apply_library_and_set_scores(
        client, make_user, auth_headers, pdf_bytes, _LIBRARY_SORT_PLAN,
        upload_order=["dan.pdf", "none.pdf", "bob.pdf", "zed.pdf", "cat.pdf", "amy.pdf"],
    )
    rows = client.get(
        f"/api/applications/job/{job_id}", params={"sort": "applied_at"}, headers=auth_headers(recruiter),
    ).json()
    assert [r["applicant_name"] for r in rows][:3] == ["zed.pdf", "bob.pdf", "amy.pdf"]
    assert rows[3]["applicant_name"] in ("cat.pdf", "dan.pdf")  # same timestamp: id breaks the tie
    assert rows[-1]["applicant_name"] == "none.pdf"


def test_applicant_paging_never_repeats_or_skips_rows(client, make_user, auth_headers, pdf_bytes):
    job_id, recruiter = _apply_library_and_set_scores(
        client, make_user, auth_headers, pdf_bytes, _LIBRARY_SORT_PLAN,
        upload_order=["dan.pdf", "none.pdf", "bob.pdf", "zed.pdf", "cat.pdf", "amy.pdf"],
    )
    full = [r["id"] for r in client.get(f"/api/applications/job/{job_id}", headers=auth_headers(recruiter)).json()]
    paged = []
    for offset in (0, 2, 4):
        page = client.get(
            f"/api/applications/job/{job_id}", params={"limit": 2, "offset": offset}, headers=auth_headers(recruiter),
        ).json()
        paged += [r["id"] for r in page]
    assert paged == full
    assert len(set(paged)) == 6


# ---------------------------------------------------------------------------
# Recruiter bulk apply
#   POST /api/applications/job/{job_id}/bulk         (resumes already in the library)
#   POST /api/applications/job/{job_id}/bulk-upload  (upload files + apply in one step)
# ---------------------------------------------------------------------------

def _bulk_upload_library(client, auth_headers, uploader, pdf_bytes, names, skills_status=ResumeExtractionStatus.DONE):
    """Recruiter bulk-uploads resumes into the library (owner_id NULL), then
    simulates the extraction worker. Returns {filename: resume_id}."""
    files = [("files", (n, pdf_bytes(f"Resume {n}"), "application/pdf")) for n in names]
    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(uploader))
    assert resp.status_code == 200
    ids = {r["original_filename"]: r["resume"]["id"] for r in resp.json() if r["success"]}
    session = TestSessionLocal()
    try:
        session.query(Resume).filter(Resume.uploaded_by_id == uploader.id).update(
            {"skills_extraction_status": skills_status}
        )
        session.commit()
    finally:
        session.close()
    return ids


def test_bulk_apply_applies_every_library_resume(client, make_user, auth_headers, pdf_bytes, dispatched):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    ids = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, ["a.pdf", "b.pdf", "c.pdf"])

    resp = client.post(
        f"/api/applications/job/{job_id}/bulk",
        json={"resume_ids": list(ids.values())}, headers=auth_headers(recruiter),
    )
    assert resp.status_code == 200
    assert [r["success"] for r in resp.json()] == [True, True, True]
    assert len(dispatched["score"]) == 3  # each one queued for scoring

    applicants = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(recruiter)).json()
    assert len(applicants) == 3
    assert {a["resume_filename"] for a in applicants} == {"a.pdf", "b.pdf", "c.pdf"}
    # No account behind these: identified by file name, tagged with who added them.
    assert all(a["user_id"] is None for a in applicants)
    assert {a["applicant_name"] for a in applicants} == {"a.pdf", "b.pdf", "c.pdf"}
    assert all(a["submitted_by_email"] == recruiter.email for a in applicants)


def test_bulk_apply_is_partial_and_skips_duplicates(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    ids = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, ["a.pdf", "b.pdf"])
    url = f"/api/applications/job/{job_id}/bulk"

    first = client.post(url, json={"resume_ids": [ids["a.pdf"]]}, headers=auth_headers(recruiter))
    assert first.json()[0]["success"] is True

    # a.pdf again (duplicate), b.pdf (fine), and an id that doesn't exist.
    ghost = "00000000-0000-0000-0000-000000000000"
    resp = client.post(url, json={"resume_ids": [ids["a.pdf"], ids["b.pdf"], ghost]}, headers=auth_headers(recruiter))
    assert resp.status_code == 200
    by_id = {r["resume_id"]: r for r in resp.json() if r["resume_id"]}
    assert by_id[ids["a.pdf"]]["success"] is False
    assert "Already applied" in by_id[ids["a.pdf"]]["error"]
    assert by_id[ids["b.pdf"]]["success"] is True
    assert [r for r in resp.json() if r["resume_id"] is None][0]["error"] == "Resume not found."

    assert len(client.get(f"/api/applications/job/{job_id}", headers=auth_headers(recruiter)).json()) == 2


def test_bulk_apply_ignores_duplicate_ids_in_one_request(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    ids = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, ["a.pdf"])
    rid = ids["a.pdf"]
    resp = client.post(
        f"/api/applications/job/{job_id}/bulk", json={"resume_ids": [rid, rid, rid]},
        headers=auth_headers(recruiter),
    )
    assert [r["success"] for r in resp.json()] == [True]


def test_bulk_apply_accepts_resume_still_processing_but_not_failed(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    pending = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, ["p.pdf"], ResumeExtractionStatus.PENDING)
    failed = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, ["f.pdf"], ResumeExtractionStatus.PENDING)
    session = TestSessionLocal()
    session.query(Resume).filter(Resume.id == failed["f.pdf"]).update({"skills_extraction_status": ResumeExtractionStatus.FAILED})
    session.commit()
    session.close()

    resp = client.post(
        f"/api/applications/job/{job_id}/bulk",
        json={"resume_ids": [pending["p.pdf"], failed["f.pdf"]]}, headers=auth_headers(recruiter),
    )
    ok, bad = resp.json()
    assert ok["success"] is True
    assert bad["success"] is False and "couldn't be read" in bad["error"]


def test_bulk_apply_refuses_candidate_owned_and_archived_resumes(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    superuser, _ = make_user(role=UserRole.SUPERUSER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    owned_id = client.get("/api/resumes", headers=auth_headers(candidate)).json()[0]["id"]
    ids = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, ["x.pdf"])
    client.patch(f"/api/resumes/{ids['x.pdf']}/archive", params={"archived": True}, headers=auth_headers(recruiter))
    url = f"/api/applications/job/{job_id}/bulk"
    body = {"resume_ids": [owned_id, ids["x.pdf"]]}

    # Superuser can use any unowned resume, so they see the real reasons.
    owned, archived = client.post(url, json=body, headers=auth_headers(superuser)).json()
    assert owned["success"] is False and "candidate account" in owned["error"]
    assert archived["success"] is False and "archived" in archived["error"]

    # A recruiter didn't upload the candidate's resume: it reads as not found.
    owned, archived = client.post(url, json=body, headers=auth_headers(recruiter)).json()
    assert owned["success"] is False and owned["error"] == "Resume not found."
    assert archived["success"] is False and "archived" in archived["error"]


def test_bulk_apply_recruiter_cannot_use_another_recruiters_resumes(client, make_user, auth_headers, pdf_bytes):
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, r1, pdf_bytes)
    theirs = _bulk_upload_library(client, auth_headers, r2, pdf_bytes, ["theirs.pdf"])

    resp = client.post(
        f"/api/applications/job/{job_id}/bulk", json={"resume_ids": [theirs["theirs.pdf"]]},
        headers=auth_headers(r1),
    )
    assert resp.json()[0]["success"] is False
    assert resp.json()[0]["error"] == "Resume not found."


def test_bulk_apply_superuser_can_apply_on_any_job_with_any_unowned_resume(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    superuser, _ = make_user(role=UserRole.SUPERUSER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    ids = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, ["a.pdf"])

    resp = client.post(
        f"/api/applications/job/{job_id}/bulk", json={"resume_ids": [ids["a.pdf"]]},
        headers=auth_headers(superuser),
    )
    assert resp.json()[0]["success"] is True
    [row] = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(superuser)).json()
    assert row["submitted_by_email"] == superuser.email


def test_bulk_apply_permissions_and_job_state(client, make_user, auth_headers, pdf_bytes):
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, r1, pdf_bytes)
    ids = _bulk_upload_library(client, auth_headers, r1, pdf_bytes, ["a.pdf"])
    body = {"resume_ids": [ids["a.pdf"]]}
    url = f"/api/applications/job/{job_id}/bulk"

    assert client.post(url, json=body).status_code == 401
    assert client.post(url, json=body, headers=auth_headers(candidate)).status_code == 403
    assert client.post(url, json=body, headers=auth_headers(r2)).status_code == 403  # not their job
    assert client.post(
        "/api/applications/job/00000000-0000-0000-0000-000000000000/bulk",
        json=body, headers=auth_headers(r1),
    ).status_code == 404
    assert client.post(url, json={"resume_ids": []}, headers=auth_headers(r1)).status_code == 422

    client.patch(f"/api/jobs/{job_id}", json={"status": "closed"}, headers=auth_headers(r1))
    assert client.post(url, json=body, headers=auth_headers(r1)).status_code == 400


def test_bulk_upload_and_apply_creates_resumes_and_applications(client, make_user, auth_headers, pdf_bytes, docx_bytes, dispatched):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    files = [
        ("files", ("one.pdf", pdf_bytes("one"), "application/pdf")),
        ("files", ("two.docx", docx_bytes("two"),
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ("files", ("bad.txt", b"nope", "text/plain")),
    ]
    resp = client.post(f"/api/applications/job/{job_id}/bulk-upload", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 200
    ok1, ok2, bad = resp.json()
    assert ok1["success"] and ok2["success"]
    assert bad["success"] is False and "PDF or DOCX" in bad["error"]
    assert len(dispatched["resume"]) == 2  # extraction queued for the two that were stored

    # They are real library resumes too: unowned, uploaded by the recruiter.
    library = client.get("/api/resumes", headers=auth_headers(recruiter)).json()
    assert {r["original_filename"] for r in library} == {"one.pdf", "two.docx"}
    assert all(r["owner_id"] is None and r["uploaded_by_id"] == str(recruiter.id) for r in library)

    applicants = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(recruiter)).json()
    assert {a["resume_filename"] for a in applicants} == {"one.pdf", "two.docx"}


def test_bulk_upload_and_apply_permissions(client, make_user, auth_headers, pdf_bytes):
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, r1, pdf_bytes)
    url = f"/api/applications/job/{job_id}/bulk-upload"

    def files():
        return [("files", ("a.pdf", pdf_bytes("a"), "application/pdf"))]

    assert client.post(url, files=files(), headers=auth_headers(candidate)).status_code == 403
    assert client.post(url, files=files(), headers=auth_headers(r2)).status_code == 403
    assert client.get("/api/resumes", headers=auth_headers(r1)).json() == []  # nothing stored on rejection


def test_job_owner_can_remove_a_recruiter_submitted_application(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    other, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    ids = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, ["a.pdf"])
    client.post(f"/api/applications/job/{job_id}/bulk", json={"resume_ids": [ids["a.pdf"]]}, headers=auth_headers(recruiter))
    app_id = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(recruiter)).json()[0]["id"]

    assert client.delete(f"/api/applications/{app_id}", headers=auth_headers(other)).status_code == 404
    assert client.delete(f"/api/applications/{app_id}", headers=auth_headers(recruiter)).status_code == 204
    assert client.get(f"/api/applications/job/{job_id}", headers=auth_headers(recruiter)).json() == []


def test_mixed_applicants_list_sorts_and_renders_both_kinds(client, make_user, auth_headers, pdf_bytes):
    """Candidate-submitted and recruiter-submitted applications live in the same list."""
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    client.post("/api/applications", json={"job_id": job_id}, headers=auth_headers(candidate))
    ids = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, ["lib.pdf"])
    client.post(f"/api/applications/job/{job_id}/bulk", json={"resume_ids": [ids["lib.pdf"]]}, headers=auth_headers(recruiter))

    for sort in ("score", "applied_at"):
        rows = client.get(f"/api/applications/job/{job_id}", params={"sort": sort}, headers=auth_headers(recruiter)).json()
        assert len(rows) == 2
        assert {r["user_id"] for r in rows} == {str(candidate.id), None}
