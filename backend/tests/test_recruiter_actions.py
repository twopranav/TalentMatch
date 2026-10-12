"""Recruiter notes + optional manual score (routes/recruiter_actions.py)."""
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from conftest import TestSessionLocal  # tests/ is on sys.path (no __init__.py)
from test_applications import _published_job, _upload_resume

from app.models.application import Application
from app.models.application_note import ApplicationNote
from app.models.audit_log import AuditLog
from app.models.user import UserRole


def _apply(client, auth_headers, recruiter, candidate, pdf_bytes):
    """A published job owned by `recruiter` with one application from
    `candidate`. Returns (job_id, application_id)."""
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    app_id = client.post(
        "/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate),
    ).json()["id"]
    return job_id, app_id


def _set_ai_score(app_id, score):
    """Stands in for the scoring worker, which isn't running in tests."""
    session = TestSessionLocal()
    try:
        session.query(Application).filter(Application.id == uuid.UUID(app_id)).update(
            {"match_score": score, "match_status": "done"}
        )
        session.commit()
    finally:
        session.close()


def _applicant_row(client, auth_headers, user, job_id, app_id):
    rows = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(user)).json()
    return next(r for r in rows if r["id"] == app_id)


@pytest.fixture()
def setup(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    candidate, _ = make_user(role=UserRole.USER)
    job_id, app_id = _apply(client, auth_headers, recruiter, candidate, pdf_bytes)
    return {"recruiter": recruiter, "candidate": candidate, "job_id": job_id, "app_id": app_id}


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------

def test_owner_adds_notes_and_lists_them_newest_first(client, auth_headers, setup):
    h = auth_headers(setup["recruiter"])
    url = f"/api/applications/{setup['app_id']}/notes"

    first = client.post(url, json={"body": "Strong on backend."}, headers=h)
    assert first.status_code == 201
    assert first.json()["author_email"] == setup["recruiter"].email
    assert first.json()["author_id"] == str(setup["recruiter"].id)
    client.post(url, json={"body": "Call scheduled for Friday."}, headers=h)

    notes = client.get(url, headers=h).json()
    assert [n["body"] for n in notes] == ["Call scheduled for Friday.", "Strong on backend."]


def test_note_with_no_notes_yet_lists_empty(client, auth_headers, setup):
    resp = client.get(f"/api/applications/{setup['app_id']}/notes", headers=auth_headers(setup["recruiter"]))
    assert resp.status_code == 200
    assert resp.json() == []


def test_note_body_is_trimmed(client, auth_headers, setup):
    resp = client.post(
        f"/api/applications/{setup['app_id']}/notes", json={"body": "  padded  \n"},
        headers=auth_headers(setup["recruiter"]),
    )
    assert resp.status_code == 201
    assert resp.json()["body"] == "padded"


@pytest.mark.parametrize("body", ["", "   ", "\n\t"])
def test_blank_note_rejected(client, auth_headers, setup, body):
    resp = client.post(
        f"/api/applications/{setup['app_id']}/notes", json={"body": body},
        headers=auth_headers(setup["recruiter"]),
    )
    assert resp.status_code == 422


def test_overlong_note_rejected(client, auth_headers, setup):
    ok = client.post(
        f"/api/applications/{setup['app_id']}/notes", json={"body": "x" * 2000},
        headers=auth_headers(setup["recruiter"]),
    )
    too_long = client.post(
        f"/api/applications/{setup['app_id']}/notes", json={"body": "x" * 2001},
        headers=auth_headers(setup["recruiter"]),
    )
    assert ok.status_code == 201
    assert too_long.status_code == 422


def test_non_owning_recruiter_cannot_read_or_add_notes(client, make_user, auth_headers, setup):
    other, _ = make_user(role=UserRole.RECRUITER)
    url = f"/api/applications/{setup['app_id']}/notes"
    assert client.get(url, headers=auth_headers(other)).status_code == 403
    assert client.post(url, json={"body": "hi"}, headers=auth_headers(other)).status_code == 403


def test_candidate_cannot_read_or_add_notes(client, auth_headers, setup):
    """The applicant must never be able to read what recruiters wrote about them."""
    url = f"/api/applications/{setup['app_id']}/notes"
    h = auth_headers(setup["candidate"])
    assert client.get(url, headers=h).status_code == 403
    assert client.post(url, json={"body": "hi"}, headers=h).status_code == 403


def test_unauthenticated_cannot_use_notes(client, setup):
    url = f"/api/applications/{setup['app_id']}/notes"
    assert client.get(url).status_code == 401
    assert client.post(url, json={"body": "hi"}).status_code == 401


def test_admin_can_add_and_read_notes_on_any_job(client, make_user, auth_headers, setup):
    admin, _ = make_user(role=UserRole.ADMIN)
    url = f"/api/applications/{setup['app_id']}/notes"
    assert client.post(url, json={"body": "admin note"}, headers=auth_headers(admin)).status_code == 201
    notes = client.get(url, headers=auth_headers(admin)).json()
    assert notes[0]["author_email"] == admin.email


def test_owner_sees_notes_other_recruiters_wrote(client, make_user, auth_headers, setup):
    admin, _ = make_user(role=UserRole.ADMIN)
    url = f"/api/applications/{setup['app_id']}/notes"
    client.post(url, json={"body": "from admin"}, headers=auth_headers(admin))
    notes = client.get(url, headers=auth_headers(setup["recruiter"])).json()
    assert [n["body"] for n in notes] == ["from admin"]


def test_notes_404_for_missing_application(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    url = f"/api/applications/{uuid.uuid4()}/notes"
    assert client.get(url, headers=auth_headers(recruiter)).status_code == 404
    assert client.post(url, json={"body": "hi"}, headers=auth_headers(recruiter)).status_code == 404


def test_adding_a_note_writes_an_audit_row_carrying_the_job_id(client, db, auth_headers, setup):
    resp = client.post(
        f"/api/applications/{setup['app_id']}/notes", json={"body": "audited"},
        headers=auth_headers(setup["recruiter"]),
    )
    row = db.query(AuditLog).filter(
        AuditLog.resource_type == "application_note", AuditLog.resource_id == uuid.UUID(resp.json()["id"]),
    ).one()
    assert row.action == "create"
    assert row.actor_email == setup["recruiter"].email
    assert row.after["body"] == "audited"
    assert row.after["job_id"] == setup["job_id"]


def test_notes_are_deleted_with_their_application(client, db, auth_headers, setup):
    client.post(
        f"/api/applications/{setup['app_id']}/notes", json={"body": "gone soon"},
        headers=auth_headers(setup["recruiter"]),
    )
    assert db.query(ApplicationNote).count() == 1
    assert client.delete(f"/api/applications/{setup['app_id']}", headers=auth_headers(setup["candidate"])).status_code == 204
    db.expire_all()
    assert db.query(ApplicationNote).count() == 0


def test_candidate_view_never_exposes_notes_or_manual_score(client, auth_headers, setup):
    h = auth_headers(setup["recruiter"])
    client.post(f"/api/applications/{setup['app_id']}/notes", json={"body": "secret opinion"}, headers=h)
    client.patch(f"/api/applications/{setup['app_id']}/manual-score", json={"manual_score": 42}, headers=h)

    mine = client.get("/api/applications/me", headers=auth_headers(setup["candidate"]))
    assert mine.status_code == 200
    assert "secret opinion" not in mine.text
    assert "manual_score" not in mine.text


# ---------------------------------------------------------------------------
# Manual score
# ---------------------------------------------------------------------------

def test_manual_score_is_null_until_set(client, auth_headers, setup):
    row = _applicant_row(client, auth_headers, setup["recruiter"], setup["job_id"], setup["app_id"])
    assert row["manual_score"] is None


def test_set_manual_score_and_see_it_in_the_applicants_list(client, auth_headers, setup):
    h = auth_headers(setup["recruiter"])
    resp = client.patch(f"/api/applications/{setup['app_id']}/manual-score", json={"manual_score": 82.5}, headers=h)
    assert resp.status_code == 200
    assert resp.json() == {"id": setup["app_id"], "manual_score": 82.5}
    row = _applicant_row(client, auth_headers, setup["recruiter"], setup["job_id"], setup["app_id"])
    assert row["manual_score"] == 82.5


def test_manual_score_can_be_cleared_with_null(client, auth_headers, setup):
    h = auth_headers(setup["recruiter"])
    url = f"/api/applications/{setup['app_id']}/manual-score"
    client.patch(url, json={"manual_score": 70}, headers=h)
    resp = client.patch(url, json={"manual_score": None}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["manual_score"] is None


@pytest.mark.parametrize("value", [0, 100, 0.0, 99.9])
def test_manual_score_boundaries_accepted(client, auth_headers, setup, value):
    resp = client.patch(
        f"/api/applications/{setup['app_id']}/manual-score", json={"manual_score": value},
        headers=auth_headers(setup["recruiter"]),
    )
    assert resp.status_code == 200
    assert resp.json()["manual_score"] == value


@pytest.mark.parametrize("value", [-0.1, -5, 100.1, 1000, "abc"])
def test_manual_score_out_of_range_or_not_a_number_rejected(client, auth_headers, setup, value):
    resp = client.patch(
        f"/api/applications/{setup['app_id']}/manual-score", json={"manual_score": value},
        headers=auth_headers(setup["recruiter"]),
    )
    assert resp.status_code == 422


def test_empty_body_does_not_silently_clear_the_score(client, auth_headers, setup):
    h = auth_headers(setup["recruiter"])
    url = f"/api/applications/{setup['app_id']}/manual-score"
    client.patch(url, json={"manual_score": 55}, headers=h)
    assert client.patch(url, json={}, headers=h).status_code == 422
    row = _applicant_row(client, auth_headers, setup["recruiter"], setup["job_id"], setup["app_id"])
    assert row["manual_score"] == 55


def test_manual_score_never_touches_the_ai_score(client, auth_headers, setup):
    _set_ai_score(setup["app_id"], 61.2)
    h = auth_headers(setup["recruiter"])
    client.patch(f"/api/applications/{setup['app_id']}/manual-score", json={"manual_score": 95}, headers=h)

    row = _applicant_row(client, auth_headers, setup["recruiter"], setup["job_id"], setup["app_id"])
    assert row["match_score"] == 61.2
    assert row["manual_score"] == 95
    assert row["match_status"] == "done"


def test_rescoring_does_not_wipe_the_manual_score(client, auth_headers, setup):
    h = auth_headers(setup["recruiter"])
    client.patch(f"/api/applications/{setup['app_id']}/manual-score", json={"manual_score": 88}, headers=h)
    assert client.post(f"/api/applications/job/{setup['job_id']}/rescore", headers=h).status_code == 202
    row = _applicant_row(client, auth_headers, setup["recruiter"], setup["job_id"], setup["app_id"])
    assert row["manual_score"] == 88


def test_non_owning_recruiter_cannot_set_manual_score(client, make_user, auth_headers, setup):
    other, _ = make_user(role=UserRole.RECRUITER)
    resp = client.patch(
        f"/api/applications/{setup['app_id']}/manual-score", json={"manual_score": 10}, headers=auth_headers(other),
    )
    assert resp.status_code == 403


def test_candidate_cannot_set_their_own_manual_score(client, auth_headers, setup):
    resp = client.patch(
        f"/api/applications/{setup['app_id']}/manual-score", json={"manual_score": 100},
        headers=auth_headers(setup["candidate"]),
    )
    assert resp.status_code == 403


def test_admin_can_set_manual_score_on_any_job(client, make_user, auth_headers, setup):
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.patch(
        f"/api/applications/{setup['app_id']}/manual-score", json={"manual_score": 64}, headers=auth_headers(admin),
    )
    assert resp.status_code == 200


def test_manual_score_404_for_missing_application(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    resp = client.patch(
        f"/api/applications/{uuid.uuid4()}/manual-score", json={"manual_score": 50}, headers=auth_headers(recruiter),
    )
    assert resp.status_code == 404


def test_manual_score_change_is_audited_with_before_and_after(client, db, auth_headers, setup):
    h = auth_headers(setup["recruiter"])
    url = f"/api/applications/{setup['app_id']}/manual-score"
    client.patch(url, json={"manual_score": 40}, headers=h)
    client.patch(url, json={"manual_score": 75}, headers=h)

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.resource_type == "application", AuditLog.resource_id == uuid.UUID(setup["app_id"]),
                AuditLog.action == "update")
        .order_by(AuditLog.created_at.asc(), AuditLog.id.asc())
        .all()
    )
    assert [(r.before["manual_score"], r.after["manual_score"]) for r in rows] == [(None, 40), (40, 75)]
    assert rows[0].actor_email == setup["recruiter"].email


def test_setting_the_same_manual_score_again_writes_no_audit_row(client, db, auth_headers, setup):
    h = auth_headers(setup["recruiter"])
    url = f"/api/applications/{setup['app_id']}/manual-score"
    client.patch(url, json={"manual_score": 40}, headers=h)
    client.patch(url, json={"manual_score": 40}, headers=h)
    updates = db.query(AuditLog).filter(
        AuditLog.resource_type == "application", AuditLog.resource_id == uuid.UUID(setup["app_id"]),
        AuditLog.action == "update",
    ).count()
    assert updates == 1


def test_database_itself_refuses_an_out_of_range_manual_score(db, client, auth_headers, setup):
    """The API validates too, but the CHECK constraint is the backstop for any
    other code path (scripts, future endpoints)."""
    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE applications SET manual_score = 150 WHERE id = :id"), {"id": setup["app_id"]},
        )
        db.commit()
    db.rollback()
