"""GET /api/audit (routes/audit.py): admin/superuser see everything, a
recruiter sees only their own jobs, everyone else is refused."""
import uuid

import pytest

from conftest import TestSessionLocal  # tests/ is on sys.path (no __init__.py)
from test_applications import _published_job, _upload_resume

from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.user import UserRole


def _apply(client, auth_headers, recruiter, candidate, pdf_bytes):
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    _upload_resume(client, auth_headers, candidate, pdf_bytes)
    app_id = client.post(
        "/api/applications", json={"job_id": job_id, "resume_id": None}, headers=auth_headers(candidate),
    ).json()["id"]
    return job_id, app_id


def _fetch(client, headers, **params):
    resp = client.get("/api/audit", params={"limit": 200, **params}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _job_of(row):
    """Which job an audit row is about, however it stores that."""
    if row["resource_type"] == "job":
        return row["resource_id"]
    snap = row["after"] or row["before"] or {}
    return snap.get("job_id")


@pytest.fixture()
def world(client, make_user, auth_headers, pdf_bytes):
    """Two recruiters, each with a job and one applicant. recruiter1 has also
    shortlisted their applicant and written a note; recruiter2 has written a
    note on theirs."""
    r1, _ = make_user(role=UserRole.RECRUITER)
    r2, _ = make_user(role=UserRole.RECRUITER)
    c1, _ = make_user(role=UserRole.USER)
    c2, _ = make_user(role=UserRole.USER)
    job1, app1 = _apply(client, auth_headers, r1, c1, pdf_bytes)
    job2, app2 = _apply(client, auth_headers, r2, c2, pdf_bytes)
    client.patch(f"/api/applications/{app1}/status", json={"status": "shortlisted"}, headers=auth_headers(r1))
    client.post(f"/api/applications/{app1}/notes", json={"body": "r1 note"}, headers=auth_headers(r1))
    client.post(f"/api/applications/{app2}/notes", json={"body": "r2 note"}, headers=auth_headers(r2))
    return dict(r1=r1, r2=r2, c1=c1, c2=c2, job1=job1, app1=app1, job2=job2, app2=app2)


# ---------------------------------------------------------------------------
# Who may call it
# ---------------------------------------------------------------------------

def test_unauthenticated_gets_401(client):
    assert client.get("/api/audit").status_code == 401


def test_plain_user_gets_403(client, make_user, auth_headers, world):
    assert client.get("/api/audit", headers=auth_headers(world["c1"])).status_code == 403


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERUSER])
def test_admin_and_superuser_see_the_complete_trail(client, db, make_user, auth_headers, world, role):
    # Rows about users / resumes only ever exist for admin-level eyes.
    db.add_all([
        AuditLog(action="update", resource_type="user", resource_id=uuid.uuid4(), before={"a": 1}, after={"a": 2}),
        AuditLog(action="create", resource_type="resume", resource_id=uuid.uuid4(), after={"x": 1}),
    ])
    db.commit()
    viewer, _ = make_user(role=role)

    rows = _fetch(client, auth_headers(viewer))
    types = {r["resource_type"] for r in rows}
    assert {"job", "application", "application_note", "user", "resume"} <= types
    assert {world["job1"], world["job2"]} <= {_job_of(r) for r in rows}
    total = client.get("/api/audit", params={"limit": 1}, headers=auth_headers(viewer)).headers["X-Total-Count"]
    assert int(total) == db.query(AuditLog).count()


# ---------------------------------------------------------------------------
# Recruiter scoping
# ---------------------------------------------------------------------------

def test_recruiter_sees_only_entries_about_their_own_jobs(client, auth_headers, world):
    rows = _fetch(client, auth_headers(world["r1"]))
    assert rows, "recruiter should see their own history"
    assert {_job_of(r) for r in rows} == {world["job1"]}
    # ...and that history includes every kind of thing they did on it.
    assert {"job", "application", "application_note"} <= {r["resource_type"] for r in rows}


def test_recruiter_never_sees_another_recruiters_entries(client, auth_headers, world):
    rows = _fetch(client, auth_headers(world["r1"]))
    assert world["job2"] not in {_job_of(r) for r in rows}
    assert world["app2"] not in {r["resource_id"] for r in rows}
    assert "r2 note" not in str(rows)


def test_recruiter_never_sees_user_or_resume_entries(client, db, auth_headers, world):
    db.add_all([
        AuditLog(action="update", resource_type="user", resource_id=uuid.uuid4(), before={"a": 1}, after={"a": 2}),
        AuditLog(action="create", resource_type="resume", resource_id=uuid.uuid4(), after={"job_id": world["job1"]}),
    ])
    db.commit()
    rows = _fetch(client, auth_headers(world["r1"]))
    assert {r["resource_type"] for r in rows} <= {"job", "application", "application_note"}


def test_recruiter_asking_for_someone_elses_job_gets_nothing_not_an_error(client, auth_headers, world):
    rows = _fetch(client, auth_headers(world["r1"]), job_id=world["job2"])
    assert rows == []
    rows = _fetch(client, auth_headers(world["r1"]), resource_id=world["app2"])
    assert rows == []


def test_recruiter_keeps_history_of_a_withdrawn_application(client, auth_headers, world):
    """Withdrawing deletes the application row, but its history must remain."""
    assert client.delete(f"/api/applications/{world['app1']}", headers=auth_headers(world["c1"])).status_code == 204
    rows = _fetch(client, auth_headers(world["r1"]), resource_id=world["app1"])
    actions = [r["action"] for r in rows]
    assert "delete" in actions and "create" in actions


def test_recruiter_keeps_history_after_deleting_their_job(client, auth_headers, world):
    assert client.delete(f"/api/jobs/{world['job1']}", headers=auth_headers(world["r1"])).status_code == 204
    rows = _fetch(client, auth_headers(world["r1"]))
    by_type = {(r["resource_type"], r["action"]) for r in rows}
    assert ("job", "delete") in by_type
    # the job is gone from the jobs table, but its applications' history still resolves to it
    assert ("application", "update") in by_type
    assert ("application_note", "create") in by_type
    # and still nothing from the other recruiter
    assert world["job2"] not in {_job_of(r) for r in rows}


def test_deleted_job_history_does_not_leak_to_another_recruiter(client, auth_headers, world):
    client.delete(f"/api/jobs/{world['job1']}", headers=auth_headers(world["r1"]))
    rows = _fetch(client, auth_headers(world["r2"]))
    assert world["job1"] not in {_job_of(r) for r in rows}


# ---------------------------------------------------------------------------
# Filters, ordering, paging
# ---------------------------------------------------------------------------

def test_filter_by_resource_type(client, auth_headers, world):
    rows = _fetch(client, auth_headers(world["r1"]), resource_type="application_note")
    assert rows and {r["resource_type"] for r in rows} == {"application_note"}
    assert rows[0]["after"]["body"] == "r1 note"


def test_filter_by_resource_id_gives_one_records_history_newest_first(client, auth_headers, world):
    rows = _fetch(client, auth_headers(world["r1"]), resource_id=world["app1"])
    assert {r["resource_id"] for r in rows} == {world["app1"]}
    assert [r["action"] for r in rows] == ["update", "create"]  # shortlisted, then applied


def test_filter_by_job_id_covers_the_job_its_applications_and_notes(client, auth_headers, make_user, world):
    admin, _ = make_user(role=UserRole.ADMIN)
    rows = _fetch(client, auth_headers(admin), job_id=world["job2"])
    assert {_job_of(r) for r in rows} == {world["job2"]}
    assert {"job", "application", "application_note"} <= {r["resource_type"] for r in rows}


def test_filter_by_action_and_actor(client, auth_headers, world):
    h = auth_headers(world["r1"])
    updates = _fetch(client, h, action="update")
    assert updates and {r["action"] for r in updates} == {"update"}
    mine = _fetch(client, h, actor_id=str(world["r1"].id))
    assert mine and {r["actor_email"] for r in mine} == {world["r1"].email}
    assert _fetch(client, h, actor_id=str(uuid.uuid4())) == []


def test_results_are_newest_first_and_paging_never_repeats_or_skips(client, auth_headers, world):
    h = auth_headers(world["r1"])
    everything = _fetch(client, h)
    stamps = [r["created_at"] for r in everything]
    assert stamps == sorted(stamps, reverse=True)

    page1 = client.get("/api/audit", params={"limit": 2, "offset": 0}, headers=h)
    page2 = client.get("/api/audit", params={"limit": 2, "offset": 2}, headers=h)
    assert int(page1.headers["X-Total-Count"]) == len(everything)
    assert [r["id"] for r in page1.json() + page2.json()] == [r["id"] for r in everything[:4]]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"resource_id": "not-a-uuid"}])
def test_bad_query_params_rejected(client, auth_headers, world, params):
    assert client.get("/api/audit", params=params, headers=auth_headers(world["r1"])).status_code == 422


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

def test_changed_fields_name_what_actually_changed(client, auth_headers, world):
    rows = _fetch(client, auth_headers(world["r1"]), resource_id=world["app1"], action="update")
    changed = rows[0]["changed_fields"]
    assert "status" in changed
    assert "shortlist_stage" in changed  # entering the shortlist starts a stage
    assert "updated_at" not in changed   # changes on every write, so it would be noise
    assert "job_id" not in changed       # untouched fields are not listed


def test_create_and_delete_rows_have_no_changed_fields(client, auth_headers, world):
    client.delete(f"/api/applications/{world['app1']}", headers=auth_headers(world["c1"]))
    rows = _fetch(client, auth_headers(world["r1"]), resource_id=world["app1"])
    for r in rows:
        if r["action"] in ("create", "delete"):
            assert r["changed_fields"] == []


def test_manual_score_change_shows_up_as_a_changed_field(client, auth_headers, world):
    h = auth_headers(world["r1"])
    client.patch(f"/api/applications/{world['app1']}/manual-score", json={"manual_score": 77}, headers=h)
    latest = _fetch(client, h, resource_id=world["app1"])[0]
    assert latest["changed_fields"] == ["manual_score"]
    assert (latest["before"]["manual_score"], latest["after"]["manual_score"]) == (None, 77)


def test_bulky_match_details_is_left_out_of_the_response_but_kept_in_the_database(client, db, auth_headers, world):
    session = TestSessionLocal()
    try:
        session.query(Application).filter(Application.id == uuid.UUID(world["app1"])).update(
            {"match_details": {"skills": ["a" * 50] * 20}}
        )
        session.commit()
    finally:
        session.close()
    h = auth_headers(world["r1"])
    client.patch(f"/api/applications/{world['app1']}/status", json={"status": "rejected"}, headers=h)

    latest = _fetch(client, h, resource_id=world["app1"])[0]
    assert "match_details" not in latest["before"] and "match_details" not in latest["after"]
    stored = db.query(AuditLog).filter(AuditLog.id == uuid.UUID(latest["id"])).one()
    assert "match_details" in stored.after  # the audit record itself is untouched
