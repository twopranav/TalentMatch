"""Sub-company scoping: who can read / write what, who approves signup
requests, and the superuser-only sub-company assignment endpoint.

  * recruiter: reads every job + applicant in their sub company, writes only
    jobs they posted.
  * admin: reads and writes everything in their sub company, nothing outside.
  * superuser: unrestricted.
  * only the superuser approves/rejects recruiter and admin signup requests
    and assigns sub companies.
"""
import pytest

from app.models.audit_log import AuditLog
from app.models.user import SubCompany, User, UserRole

SOLAR = SubCompany.SOLAR
PV = SubCompany.PHOTOVOLTAIC


def _post_job(client, auth_headers, owner, title="Job"):
    resp = client.post("/api/jobs", json={"title": title, "description": "Do the work"}, headers=auth_headers(owner))
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _job_ids(client, auth_headers, viewer):
    resp = client.get("/api/jobs", params={"limit": 200}, headers=auth_headers(viewer))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    items = body["items"] if isinstance(body, dict) else body
    return {j["id"] for j in items}


@pytest.fixture()
def world(client, make_user, auth_headers):
    r_solar, _ = make_user(role=UserRole.RECRUITER, sub_company=SOLAR)
    r_solar2, _ = make_user(role=UserRole.RECRUITER, sub_company=SOLAR)
    r_pv, _ = make_user(role=UserRole.RECRUITER, sub_company=PV)
    a_solar, _ = make_user(role=UserRole.ADMIN, sub_company=SOLAR)
    a_pv, _ = make_user(role=UserRole.ADMIN, sub_company=PV)
    su, _ = make_user(role=UserRole.SUPERUSER)
    return dict(
        r_solar=r_solar, r_solar2=r_solar2, r_pv=r_pv, a_solar=a_solar, a_pv=a_pv, su=su,
        job_solar=_post_job(client, auth_headers, r_solar, "Solar job"),
        job_solar2=_post_job(client, auth_headers, r_solar2, "Solar job 2"),
        job_pv=_post_job(client, auth_headers, r_pv, "PV job"),
    )


# --------------------------------------------------------------- reads

def test_recruiter_reads_every_job_in_their_sub_company_and_none_outside(client, auth_headers, world):
    ids = _job_ids(client, auth_headers, world["r_solar"])
    assert ids == {world["job_solar"], world["job_solar2"]}
    assert client.get(f"/api/jobs/{world['job_solar2']}", headers=auth_headers(world["r_solar"])).status_code == 200
    assert client.get(f"/api/jobs/{world['job_pv']}", headers=auth_headers(world["r_solar"])).status_code == 404


def test_recruiter_reads_applicants_of_a_colleagues_job_but_not_another_companys(client, auth_headers, world):
    h = auth_headers(world["r_solar"])
    assert client.get(f"/api/applications/job/{world['job_solar2']}", headers=h).status_code == 200
    assert client.get(f"/api/applications/job/{world['job_pv']}", headers=h).status_code == 403


def test_admin_reads_only_their_own_sub_company(client, auth_headers, world):
    assert _job_ids(client, auth_headers, world["a_solar"]) == {world["job_solar"], world["job_solar2"]}
    assert _job_ids(client, auth_headers, world["a_pv"]) == {world["job_pv"]}
    h = auth_headers(world["a_pv"])
    assert client.get(f"/api/jobs/{world['job_solar']}", headers=h).status_code == 404
    assert client.get(f"/api/applications/job/{world['job_solar']}", headers=h).status_code == 403


def test_superuser_reads_everything(client, auth_headers, world):
    assert _job_ids(client, auth_headers, world["su"]) == {world["job_solar"], world["job_solar2"], world["job_pv"]}


# -------------------------------------------------------------- writes

def test_recruiter_writes_only_jobs_they_posted(client, auth_headers, world):
    h = auth_headers(world["r_solar"])
    assert client.patch(f"/api/jobs/{world['job_solar']}", json={"title": "Mine, edited"}, headers=h).status_code == 200
    # a colleague's job in the same company is readable but not writable
    assert client.patch(f"/api/jobs/{world['job_solar2']}", json={"title": "Not mine"}, headers=h).status_code == 404
    assert client.delete(f"/api/jobs/{world['job_solar2']}", headers=h).status_code == 404
    assert client.patch(f"/api/jobs/{world['job_pv']}", json={"title": "Other co"}, headers=h).status_code == 404


def test_admin_writes_everything_in_their_company_and_nothing_outside(client, auth_headers, world):
    h = auth_headers(world["a_solar"])
    for job in (world["job_solar"], world["job_solar2"]):
        assert client.patch(f"/api/jobs/{job}", json={"title": "Admin edit"}, headers=h).status_code == 200
    assert client.patch(f"/api/jobs/{world['job_pv']}", json={"title": "Nope"}, headers=h).status_code == 404
    assert client.delete(f"/api/jobs/{world['job_pv']}", headers=h).status_code == 404


def test_superuser_writes_anything(client, auth_headers, world):
    h = auth_headers(world["su"])
    for job in (world["job_solar"], world["job_pv"]):
        assert client.patch(f"/api/jobs/{job}", json={"title": "God edit"}, headers=h).status_code == 200


def test_a_recruiter_moved_to_another_company_loses_access_to_the_jobs_they_left_behind(client, db, auth_headers, world):
    h_su = auth_headers(world["su"])
    resp = client.patch(f"/api/users/{world['r_solar'].id}/sub-company", json={"sub_company": SubCompany.TECHNOLOGIES.value}, headers=h_su)
    assert resp.status_code == 200
    h = auth_headers(world["r_solar"])
    assert client.get(f"/api/jobs/{world['job_solar']}", headers=h).status_code == 404
    assert client.patch(f"/api/jobs/{world['job_solar']}", json={"title": "x"}, headers=h).status_code == 404
    # the Solar admin still manages it
    assert client.patch(f"/api/jobs/{world['job_solar']}", json={"title": "kept"}, headers=auth_headers(world["a_solar"])).status_code == 200


# ----------------------------------------------- PATCH /users/{id}/sub-company

@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER, UserRole.ADMIN])
def test_sub_company_assignment_is_superuser_only(client, make_user, auth_headers, role):
    actor, _ = make_user(role=role)
    target, _ = make_user(role=UserRole.RECRUITER)
    resp = client.patch(f"/api/users/{target.id}/sub-company", json={"sub_company": PV.value}, headers=auth_headers(actor))
    assert resp.status_code == 403


def test_superuser_assigns_and_changes_sub_company_of_existing_users(client, db, make_user, auth_headers):
    su, _ = make_user(role=UserRole.SUPERUSER)
    plain, _ = make_user(role=UserRole.USER, sub_company=None)
    recruiter, _ = make_user(role=UserRole.RECRUITER, sub_company=SOLAR)
    h = auth_headers(su)

    resp = client.patch(f"/api/users/{plain.id}/sub-company", json={"sub_company": PV.value}, headers=h)
    assert resp.status_code == 200 and resp.json()["sub_company"] == PV.value
    resp = client.patch(f"/api/users/{recruiter.id}/sub-company", json={"sub_company": PV.value}, headers=h)
    assert resp.status_code == 200 and resp.json()["sub_company"] == PV.value

    db.expire_all()
    assert db.get(User, recruiter.id).sub_company == PV
    rows = db.query(AuditLog).filter(AuditLog.resource_id == recruiter.id, AuditLog.action == "update").all()
    assert len(rows) == 1
    assert rows[0].before["sub_company"] == SOLAR.value and rows[0].after["sub_company"] == PV.value


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.RECRUITER])
def test_cannot_clear_sub_company_of_admin_or_recruiter(client, make_user, auth_headers, role):
    su, _ = make_user(role=UserRole.SUPERUSER)
    target, _ = make_user(role=role, sub_company=SOLAR)
    resp = client.patch(f"/api/users/{target.id}/sub-company", json={"sub_company": None}, headers=auth_headers(su))
    assert resp.status_code == 400


def test_can_clear_sub_company_of_a_plain_user(client, make_user, auth_headers):
    su, _ = make_user(role=UserRole.SUPERUSER)
    plain, _ = make_user(role=UserRole.USER, sub_company=SOLAR)
    resp = client.patch(f"/api/users/{plain.id}/sub-company", json={"sub_company": None}, headers=auth_headers(su))
    assert resp.status_code == 200 and resp.json()["sub_company"] is None


def test_rejects_an_unknown_sub_company_and_the_superuser_as_target(client, make_user, auth_headers):
    su, _ = make_user(role=UserRole.SUPERUSER)
    plain, _ = make_user(role=UserRole.USER)
    h = auth_headers(su)
    assert client.patch(f"/api/users/{plain.id}/sub-company", json={"sub_company": "Acme"}, headers=h).status_code == 422
    assert client.patch(f"/api/users/{su.id}/sub-company", json={"sub_company": SOLAR.value}, headers=h).status_code == 400


# ------------------------------------------------- signup request approval

@pytest.mark.parametrize("requested", [UserRole.RECRUITER, UserRole.ADMIN])
def test_superuser_approval_grants_role_and_sub_company_together(client, db, make_user, auth_headers, requested):
    su, _ = make_user(role=UserRole.SUPERUSER)
    pending, _ = make_user(role=UserRole.USER, requested_role=requested, sub_company=PV)
    resp = client.post(f"/api/users/{pending.id}/approve-request", headers=auth_headers(su))
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == requested.value
    assert body["sub_company"] == PV.value
    assert body["requested_role"] is None
    db.expire_all()
    refreshed = db.get(User, pending.id)
    assert refreshed.role == requested and refreshed.sub_company == PV


def test_the_superuser_can_fix_the_sub_company_before_approving(client, make_user, auth_headers):
    su, _ = make_user(role=UserRole.SUPERUSER)
    pending, _ = make_user(role=UserRole.USER, requested_role=UserRole.RECRUITER, sub_company=SOLAR)
    h = auth_headers(su)
    assert client.patch(f"/api/users/{pending.id}/sub-company", json={"sub_company": PV.value}, headers=h).status_code == 200
    body = client.post(f"/api/users/{pending.id}/approve-request", headers=h).json()
    assert body["role"] == "recruiter" and body["sub_company"] == PV.value


def test_approval_without_a_sub_company_is_refused(client, db, make_user, auth_headers):
    su, _ = make_user(role=UserRole.SUPERUSER)
    pending, _ = make_user(role=UserRole.USER, requested_role=UserRole.RECRUITER, sub_company=None)
    resp = client.post(f"/api/users/{pending.id}/approve-request", headers=auth_headers(su))
    assert resp.status_code == 400
    db.expire_all()
    assert db.get(User, pending.id).role == UserRole.USER


@pytest.mark.parametrize("path", ["approve-request", "reject-request", "approve-recruiter-request", "reject-recruiter-request"])
def test_admins_can_no_longer_approve_or_reject_requests(client, db, make_user, auth_headers, path):
    admin, _ = make_user(role=UserRole.ADMIN, sub_company=SOLAR)
    pending, _ = make_user(role=UserRole.USER, requested_role=UserRole.RECRUITER, sub_company=SOLAR)
    resp = client.post(f"/api/users/{pending.id}/{path}", headers=auth_headers(admin))
    assert resp.status_code == 403
    db.expire_all()
    refreshed = db.get(User, pending.id)
    assert refreshed.role == UserRole.USER and refreshed.requested_role == UserRole.RECRUITER


def test_admin_sees_only_their_own_sub_companys_pending_requests(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN, sub_company=SOLAR)
    mine, _ = make_user(role=UserRole.USER, requested_role=UserRole.RECRUITER, sub_company=SOLAR)
    make_user(role=UserRole.USER, requested_role=UserRole.ADMIN, sub_company=PV)
    ids = [u["id"] for u in client.get("/api/users?pending=true", headers=auth_headers(admin)).json()]
    assert ids == [str(mine.id)]
    su, _ = make_user(role=UserRole.SUPERUSER)
    assert len(client.get("/api/users?pending=true", headers=auth_headers(su)).json()) == 2


def test_admin_user_list_is_limited_to_their_sub_company_and_hides_the_unassigned(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN, sub_company=SOLAR)
    mine, _ = make_user(role=UserRole.RECRUITER, sub_company=SOLAR)
    make_user(role=UserRole.RECRUITER, sub_company=PV)
    make_user(role=UserRole.USER, sub_company=None)
    ids = {u["id"] for u in client.get("/api/users", headers=auth_headers(admin)).json()}
    assert ids == {str(admin.id), str(mine.id)}


# --------------------------------------------------- audit + overview scope

def test_admin_audit_feed_is_scoped_to_their_sub_company(client, db, make_user, auth_headers, world):
    rows = client.get("/api/audit", params={"limit": 200}, headers=auth_headers(world["a_pv"])).json()
    job_ids = {r["resource_id"] for r in rows if r["resource_type"] == "job"}
    assert job_ids == {world["job_pv"]}
    assert all(r["resource_type"] in ("job", "application", "application_note", "user") for r in rows)
    users = {r["resource_id"] for r in rows if r["resource_type"] == "user"}
    assert users <= {str(world["a_pv"].id), str(world["r_pv"].id)}


def test_admin_audit_feed_never_includes_resume_rows(client, db, make_user, auth_headers, pdf_bytes):
    admin, _ = make_user(role=UserRole.ADMIN, sub_company=SOLAR)
    recruiter, _ = make_user(role=UserRole.RECRUITER, sub_company=SOLAR)
    files = [("files", ("a.pdf", pdf_bytes("a"), "application/pdf"))]
    assert client.post("/api/resumes/bulk", files=files, headers=auth_headers(recruiter)).status_code == 200
    assert db.query(AuditLog).filter(AuditLog.resource_type == "resume").count() >= 1
    admin_rows = client.get("/api/audit", params={"limit": 200}, headers=auth_headers(admin)).json()
    assert not [r for r in admin_rows if r["resource_type"] == "resume"]
    su, _ = make_user(role=UserRole.SUPERUSER)
    su_rows = client.get("/api/audit", params={"limit": 200}, headers=auth_headers(su)).json()
    assert [r for r in su_rows if r["resource_type"] == "resume"]


def test_admin_audit_keeps_deleted_jobs_of_their_company_visible(client, auth_headers, world):
    assert client.delete(f"/api/jobs/{world['job_solar2']}", headers=auth_headers(world["a_solar"])).status_code in (200, 204)
    rows = client.get("/api/audit", params={"limit": 200, "action": "delete"}, headers=auth_headers(world["a_solar"])).json()
    assert world["job_solar2"] in {r["resource_id"] for r in rows}
    pv_rows = client.get("/api/audit", params={"limit": 200}, headers=auth_headers(world["a_pv"])).json()
    assert world["job_solar2"] not in {r["resource_id"] for r in pv_rows}


def test_overview_scopes_requests_and_audit_feed_but_not_system_health(client, make_user, auth_headers, world):
    make_user(role=UserRole.USER, requested_role=UserRole.RECRUITER, sub_company=SOLAR)
    make_user(role=UserRole.USER, requested_role=UserRole.ADMIN, sub_company=PV)
    make_user(role=UserRole.USER, requested_role=UserRole.RECRUITER, sub_company=PV)

    solar = client.get("/api/overview", headers=auth_headers(world["a_solar"])).json()
    pv = client.get("/api/overview", headers=auth_headers(world["a_pv"])).json()
    god = client.get("/api/overview", headers=auth_headers(world["su"])).json()

    assert solar["pending_recruiter_requests"] == 1
    assert pv["pending_recruiter_requests"] == 2
    assert god["pending_recruiter_requests"] == 3
    assert {p["sub_company"] for p in pv["pending_recruiters"]} == {PV.value}
    assert {p["requested_role"] for p in pv["pending_recruiters"]} == {"admin", "recruiter"}

    # the feed carries only that company's activity; the superuser's is the widest
    assert len(solar["recent_audit_activity"]) > 0 and len(pv["recent_audit_activity"]) > 0
    solar_ids = {a["id"] for a in solar["recent_audit_activity"]}
    pv_ids = {a["id"] for a in pv["recent_audit_activity"]}
    assert not (solar_ids & pv_ids)

    # system-health items are global and identical for every admin
    for key in ("unset_llm_tasks", "unset_llm_task_names", "system_queue_depth", "quota_usage"):
        assert solar[key] == pv[key] == god[key]


def test_an_admin_with_no_sub_company_sees_nothing_scoped(client, make_user, auth_headers, world):
    lonely, _ = make_user(role=UserRole.ADMIN, sub_company=None)
    h = auth_headers(lonely)
    assert _job_ids(client, auth_headers, lonely) == set()
    assert client.get("/api/audit", headers=h).json() == []
    ov = client.get("/api/overview", headers=h).json()
    assert ov["pending_recruiter_requests"] == 0 and ov["recent_audit_activity"] == []


# ------------------------------------------------------ moving a job between companies

def _move(client, auth_headers, actor, job_id, company):
    return client.patch(f"/api/jobs/{job_id}", json={"sub_company": company}, headers=auth_headers(actor))


@pytest.mark.parametrize("actor_key", ["r_solar", "a_solar"])
def test_recruiter_and_admin_cannot_move_a_job_even_in_their_own_company(client, auth_headers, world, actor_key):
    resp = _move(client, auth_headers, world[actor_key], world["job_solar"], PV.value)
    assert resp.status_code == 403
    job = client.get(f"/api/jobs/{world['job_solar']}", headers=auth_headers(world["su"])).json()
    assert job["sub_company"] == SOLAR.value


@pytest.mark.parametrize("actor_key", ["r_solar", "a_solar"])
def test_resending_the_current_company_is_still_refused_for_non_superusers(client, auth_headers, world, actor_key):
    assert _move(client, auth_headers, world[actor_key], world["job_solar"], SOLAR.value).status_code == 403


def test_recruiter_cannot_null_out_the_company(client, auth_headers, world):
    assert _move(client, auth_headers, world["r_solar"], world["job_solar"], None).status_code == 403


def test_superuser_moves_a_job_and_visibility_follows_it(client, auth_headers, world):
    resp = _move(client, auth_headers, world["su"], world["job_solar"], PV.value)
    assert resp.status_code == 200
    assert resp.json()["sub_company"] == PV.value
    assert world["job_solar"] not in _job_ids(client, auth_headers, world["r_solar"])
    assert world["job_solar"] in _job_ids(client, auth_headers, world["a_pv"])
    # the creator stays in their old company, so they can no longer edit it
    assert client.patch(f"/api/jobs/{world['job_solar']}", json={"title": "x"}, headers=auth_headers(world["r_solar"])).status_code == 404


def test_superuser_must_choose_a_different_company(client, auth_headers, world):
    assert _move(client, auth_headers, world["su"], world["job_solar"], SOLAR.value).status_code == 400
    assert _move(client, auth_headers, world["su"], world["job_solar"], None).status_code == 400
    job = client.get(f"/api/jobs/{world['job_solar']}", headers=auth_headers(world["su"])).json()
    assert job["sub_company"] == SOLAR.value


def test_a_move_is_audited(client, db, auth_headers, world):
    assert _move(client, auth_headers, world["su"], world["job_solar"], PV.value).status_code == 200
    rows = db.query(AuditLog).filter(AuditLog.resource_type == "job", AuditLog.action == "update").all()
    assert any(PV.value in str(r.after) for r in rows)


def test_ordinary_job_edits_do_not_need_a_company(client, auth_headers, world):
    resp = client.patch(f"/api/jobs/{world['job_solar']}", json={"title": "Renamed"}, headers=auth_headers(world["r_solar"]))
    assert resp.status_code == 200
    assert resp.json()["sub_company"] == SOLAR.value
