"""
Integration tests for applicant scoring: the Celery task run against real
rows, the score-sorted applicant list, and the apply / rescore triggers.
The embedder is faked; Redis is never touched (see conftest `dispatched`).
"""

import uuid
from datetime import datetime, timezone

import pytest
from conftest import TestSessionLocal

from app.models.application import Application
from app.models.job import Job, JobExtractionStatus
from app.models.resume import Resume, ResumeExtractionStatus, ResumeStatus
from app.models.user import UserRole


@pytest.fixture(autouse=True)
def _task_env(monkeypatch):
    """Point the task at the test DB and give it a deterministic embedder."""
    from app.core import matching_tasks

    monkeypatch.setattr(matching_tasks, "SessionLocal", TestSessionLocal)
    # every distinct string gets its own axis -> only exact matches score
    def embed(texts):
        return [[1.0 if i == j else 0.0 for j in range(len(texts))] for i, _ in enumerate(texts)]
    monkeypatch.setattr(matching_tasks, "embed", embed)
    return matching_tasks


def _job(db, recruiter, *, skills=("python", "sql"), min_months=24,
         status=JobExtractionStatus.DONE):
    job = Job(
        title="Backend", description="x", created_by_id=recruiter.id,
        skills_result=list(skills) if skills is not None else None,
        skills_extraction_status=status, min_experience_months=min_months,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _resume(db, owner, *, skills=("python", "sql"), months=24,
            status=ResumeExtractionStatus.DONE):
    r = Resume(
        owner_id=owner.id, uploaded_by_id=owner.id, original_filename="r.pdf",
        content_type="application/pdf", size_bytes=1, blob_path=f"{owner.id}/{uuid.uuid4()}.pdf",
        status=ResumeStatus.UPLOADED, skills_result=list(skills),
        experience_months=months, skills_extraction_status=status,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _application(db, user, job, resume, applied_at=None):
    a = Application(user_id=user.id, job_id=job.id, resume_id=resume.id)
    if applied_at:
        a.applied_at = applied_at
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _reload(db, application):
    db.expire_all()
    return db.get(Application, application.id)


# --------------------------------------------------------------------- task

def test_task_scores_and_stores_breakdown(_task_env, db, make_user):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    cand, _ = make_user()
    job = _job(db, recruiter, skills=("python", "sql", "docker"), min_months=48)
    a = _application(db, cand, job, _resume(db, cand, skills=("python", "sql"), months=24))

    _task_env.score_application_task.run(str(a.id))

    a = _reload(db, a)
    assert a.match_status == "done"
    # skills 2/3 = 0.667; 24 months -> experience 1-exp(-0.5) = 0.393
    # -> 100 * (0.55 * 0.667 + 0.45 * 0.393) = 54.4
    assert a.match_score == pytest.approx(54.4, abs=0.1)
    assert a.match_details["missing"] == ["docker"]
    assert a.match_details["skills_score"] == pytest.approx(0.667, abs=0.001)
    assert a.match_details["experience_score"] == pytest.approx(0.393, abs=0.001)
    assert a.match_details["weights_used"] == {"skills": 0.55, "experience": 0.45}
    assert a.match_details["meets_min_experience"] is False
    assert a.matched_at is not None and a.match_error is None


def test_task_waits_while_job_skills_are_still_extracting(_task_env, db, make_user):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    cand, _ = make_user()
    job = _job(db, recruiter, status=JobExtractionStatus.PENDING)
    a = _application(db, cand, job, _resume(db, cand))

    _task_env.score_application_task.run(str(a.id))

    a = _reload(db, a)
    assert a.match_status == "pending" and a.match_score is None


def test_task_records_reason_when_jd_extraction_failed(_task_env, db, make_user):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    cand, _ = make_user()
    job = _job(db, recruiter, status=JobExtractionStatus.FAILED)
    a = _application(db, cand, job, _resume(db, cand))

    _task_env.score_application_task.run(str(a.id))

    a = _reload(db, a)
    assert a.match_status == "failed"
    assert "job description" in a.match_error.lower()


def test_task_marks_failed_on_embedder_misconfiguration(_task_env, db, make_user, monkeypatch):
    from app.core.llm_provider_registry import LLMConfigError

    recruiter, _ = make_user(role=UserRole.RECRUITER)
    cand, _ = make_user()
    job = _job(db, recruiter, skills=("react",))  # not an exact match -> needs the embedder
    a = _application(db, cand, job, _resume(db, cand, skills=("vue",)))

    def boom(texts):
        raise LLMConfigError("HF_TOKEN is not set")
    monkeypatch.setattr(_task_env, "embed", boom)

    _task_env.score_application_task.run(str(a.id))

    a = _reload(db, a)
    assert a.match_status == "failed" and "HF_TOKEN" in a.match_error


def test_task_ignores_a_deleted_application(_task_env):
    _task_env.score_application_task.run(str(uuid.uuid4()))  # must not raise


# ---------------------------------------------------------------- fan-out

def test_dispatch_for_job_queues_every_applicant(_task_env, db, make_user, dispatched):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job = _job(db, recruiter)
    ids = []
    for _i in range(3):
        cand, _ = make_user()
        ids.append(str(_application(db, cand, job, _resume(db, cand)).id))

    n = _task_env.dispatch_score_for_job(db, job.id)

    assert n == 3
    assert sorted(dispatched["score"]) == sorted(ids)


def test_apply_queues_scoring(client, make_user, auth_headers, pdf_bytes, dispatched, db):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    cand, _ = make_user()
    job = _job(db, recruiter)
    job.status = "published"
    db.commit()
    _resume(db, cand)

    resp = client.post("/api/applications", json={"job_id": str(job.id)}, headers=auth_headers(cand))

    assert resp.status_code == 201
    assert dispatched["score"] == [resp.json()["id"]]


# ------------------------------------------------------------- listing/sort

def _seed_three(db, make_user):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job = _job(db, recruiter)
    out = {}
    for name, score, when in [("low", 20.0, 3), ("high", 90.0, 1), ("unscored", None, 2), ("mid", 55.0, 4)]:
        cand, _ = make_user(email=f"{name}@test.com")
        a = _application(db, cand, job, _resume(db, cand),
                         applied_at=datetime(2026, 9, when, tzinfo=timezone.utc))
        if score is not None:
            a.match_score, a.match_status = score, "done"
            db.commit()
        out[name] = a
    return recruiter, job, out


def test_applicants_sorted_by_score_desc_unscored_last(client, db, make_user, auth_headers):
    recruiter, job, _ = _seed_three(db, make_user)

    resp = client.get(f"/api/applications/job/{job.id}", headers=auth_headers(recruiter))

    assert resp.status_code == 200
    assert [r["applicant_email"] for r in resp.json()] == [
        "high@test.com", "mid@test.com", "low@test.com", "unscored@test.com",
    ]
    assert resp.json()[0]["match_score"] == 90.0


def test_applicants_can_still_be_sorted_by_applied_date(client, db, make_user, auth_headers):
    recruiter, job, _ = _seed_three(db, make_user)

    resp = client.get(f"/api/applications/job/{job.id}?sort=applied_at", headers=auth_headers(recruiter))

    assert [r["applicant_email"] for r in resp.json()] == [
        "mid@test.com", "low@test.com", "unscored@test.com", "high@test.com",
    ]


def test_score_is_not_exposed_to_the_candidate(client, db, make_user, auth_headers):
    recruiter, job, apps = _seed_three(db, make_user)
    cand = apps["high"].user

    resp = client.get("/api/applications/me", headers=auth_headers(cand))

    assert resp.status_code == 200
    assert "match_score" not in resp.json()[0]


# ------------------------------------------------------------------ rescore

def test_rescore_queues_all_and_returns_count(client, db, make_user, auth_headers, dispatched):
    recruiter, job, apps = _seed_three(db, make_user)

    resp = client.post(f"/api/applications/job/{job.id}/rescore", headers=auth_headers(recruiter))

    assert resp.status_code == 202
    assert resp.json() == {"queued": 4}
    assert len(dispatched["score"]) == 4


def test_rescore_forbidden_for_another_recruiter(client, db, make_user, auth_headers):
    _, job, _ = _seed_three(db, make_user)
    other, _ = make_user(role=UserRole.RECRUITER)

    resp = client.post(f"/api/applications/job/{job.id}/rescore", headers=auth_headers(other))

    assert resp.status_code == 403


def test_rescore_forbidden_for_candidates(client, db, make_user, auth_headers):
    _, job, apps = _seed_three(db, make_user)

    resp = client.post(f"/api/applications/job/{job.id}/rescore", headers=auth_headers(apps["low"].user))

    assert resp.status_code == 403
