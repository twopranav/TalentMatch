"""Applicant list filters, search and total count
(GET /api/applications/job/{job_id}). Reuses the helpers from
test_applications.py; tests/ is on sys.path, so a plain import works."""
from conftest import TestSessionLocal

from app.models.resume import Resume
from app.models.user import SubCompany, UserRole
from test_applications import _bulk_upload_library, _published_job


# ---------------------------------------------------------------------------
# GET /api/applications/job/{job_id} -- filters, search, total count
# ---------------------------------------------------------------------------

def _match_details(matched, missing, proven=()):
    """Minimal match_details in the shape semantic_match.compute_match writes."""
    return {
        "score": 50.0,
        "matched": [
            {"jd_skill": s, "resume_skill": s, "similarity": 1.0, "credit": 1.0,
             "source": "work_experience" if s in proven else "skills_section",
             "tier_weight": 1.0 if s in proven else 0.35,
             "status": "proven" if s in proven else "mentioned", "evidence": 1.0}
            for s in matched
        ],
        "missing": list(missing),
    }


# filename: (score, matched, proven, missing, experience_months, status)
_FILTER_PLAN = {
    "amy.pdf": (90.0, ["Python", "SQL"], ["Python"], ["Docker"], 72, "shortlisted"),
    "bob.pdf": (70.0, ["Python"], [], ["SQL", "Docker"], 24, "applied"),
    "cat.pdf": (40.0, ["SQL"], ["SQL"], ["Python", "Docker"], None, "applied"),
    "dan.pdf": (None, None, None, None, None, "applied"),  # still being scored
}


def _library_with_filter_data(client, make_user, auth_headers, pdf_bytes):
    from app.models.application import Application, ApplicationStatus

    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    ids = _bulk_upload_library(client, auth_headers, recruiter, pdf_bytes, list(_FILTER_PLAN))
    results = client.post(
        f"/api/applications/job/{job_id}/bulk", json={"resume_ids": list(ids.values())},
        headers=auth_headers(recruiter),
    ).json()
    assert all(r["success"] for r in results)

    session = TestSessionLocal()
    try:
        for filename, (score, matched, proven, missing, months, status) in _FILTER_PLAN.items():
            details = None if matched is None else _match_details(matched, missing, proven or ())
            session.query(Application).filter(Application.resume_id == ids[filename]).update({
                "match_score": score, "match_details": details,
                "status": ApplicationStatus(status),
            })
            session.query(Resume).filter(Resume.id == ids[filename]).update({
                "experience_months": months,
                "skills_result": None if matched is None else matched + ["Kubernetes"] * (filename == "bob.pdf"),
            })
        session.commit()
    finally:
        session.close()
    return job_id, recruiter


def _names(resp):
    assert resp.status_code == 200
    return [r["applicant_name"] for r in resp.json()]


def test_applicants_total_count_header_ignores_paging(client, make_user, auth_headers, pdf_bytes):
    job_id, recruiter = _library_with_filter_data(client, make_user, auth_headers, pdf_bytes)
    url = f"/api/applications/job/{job_id}"
    resp = client.get(url, params={"limit": 2, "offset": 0}, headers=auth_headers(recruiter))
    assert len(resp.json()) == 2
    assert resp.headers["X-Total-Count"] == "4"
    resp = client.get(url, params={"limit": 2, "offset": 2, "min_score": 50}, headers=auth_headers(recruiter))
    assert resp.json() == []  # offset past the 2 rows that pass the filter
    assert resp.headers["X-Total-Count"] == "2"


def test_applicants_search_by_name_and_file_name(client, make_user, auth_headers, pdf_bytes):
    job_id, recruiter = _library_with_filter_data(client, make_user, auth_headers, pdf_bytes)
    url = f"/api/applications/job/{job_id}"
    assert _names(client.get(url, params={"q": "AM"}, headers=auth_headers(recruiter))) == ["amy.pdf"]
    assert _names(client.get(url, params={"q": "nobody"}, headers=auth_headers(recruiter))) == []
    # '%' and '_' are literal, not wildcards.
    assert _names(client.get(url, params={"q": "%"}, headers=auth_headers(recruiter))) == []
    assert _names(client.get(url, params={"q": "_"}, headers=auth_headers(recruiter))) == []


def test_applicants_filter_by_status_and_score_range(client, make_user, auth_headers, pdf_bytes):
    job_id, recruiter = _library_with_filter_data(client, make_user, auth_headers, pdf_bytes)
    url = f"/api/applications/job/{job_id}"
    assert _names(client.get(url, params={"status": "shortlisted"}, headers=auth_headers(recruiter))) == ["amy.pdf"]
    got = _names(client.get(url, params={"status": ["shortlisted", "applied"], "min_score": 40, "max_score": 70},
                            headers=auth_headers(recruiter)))
    assert got == ["bob.pdf", "cat.pdf"]  # unscored dan.pdf drops out once a score bound is set
    assert client.get(url, params={"status": "bogus"}, headers=auth_headers(recruiter)).status_code == 422


def test_applicants_filter_by_experience_years(client, make_user, auth_headers, pdf_bytes):
    job_id, recruiter = _library_with_filter_data(client, make_user, auth_headers, pdf_bytes)
    url = f"/api/applications/job/{job_id}"
    assert _names(client.get(url, params={"min_years": 5}, headers=auth_headers(recruiter))) == ["amy.pdf"]
    assert _names(client.get(url, params={"min_years": 1, "max_years": 3}, headers=auth_headers(recruiter))) == ["bob.pdf"]


def test_applicants_filter_by_jd_skills(client, make_user, auth_headers, pdf_bytes):
    job_id, recruiter = _library_with_filter_data(client, make_user, auth_headers, pdf_bytes)
    url = f"/api/applications/job/{job_id}"
    h = auth_headers(recruiter)
    # matched (proven or merely mentioned)
    assert _names(client.get(url, params={"skills_matched": "Python"}, headers=h)) == ["amy.pdf", "bob.pdf"]
    # several skills: all by default, any on request
    assert _names(client.get(url, params={"skills_matched": ["Python", "SQL"]}, headers=h)) == ["amy.pdf"]
    assert _names(client.get(url, params={"skills_matched": ["Python", "SQL"], "skill_mode": "any"}, headers=h)) == [
        "amy.pdf", "bob.pdf", "cat.pdf",
    ]
    # proven: bob only mentions Python, so he is excluded
    assert _names(client.get(url, params={"skills_proven": "Python"}, headers=h)) == ["amy.pdf"]
    # missing
    assert _names(client.get(url, params={"skills_missing": "SQL"}, headers=h)) == ["bob.pdf"]
    # mixed: knows Python but lacks Docker
    assert _names(client.get(url, params={"skills_matched": "Python", "skills_missing": "SQL"}, headers=h)) == ["bob.pdf"]


def test_applicants_filter_by_any_resume_skill(client, make_user, auth_headers, pdf_bytes):
    job_id, recruiter = _library_with_filter_data(client, make_user, auth_headers, pdf_bytes)
    url = f"/api/applications/job/{job_id}"
    assert _names(client.get(url, params={"resume_skill": "kube"}, headers=auth_headers(recruiter))) == ["bob.pdf"]


def test_applicant_filters_respect_job_ownership(client, make_user, auth_headers, pdf_bytes):
    job_id, _ = _library_with_filter_data(client, make_user, auth_headers, pdf_bytes)
    other, _ = make_user(role=UserRole.RECRUITER, sub_company=SubCompany.PHOTOVOLTAIC)
    resp = client.get(f"/api/applications/job/{job_id}", params={"q": "amy"}, headers=auth_headers(other))
    assert resp.status_code == 403
