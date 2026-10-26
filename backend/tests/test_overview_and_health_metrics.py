"""
GET /api/overview and GET /api/admin/health-metrics, plus the deprecated
/api/v1 aliases that keep a previously deployed frontend working.

test_sub_company_scoping.py already covers the *scoping* of the admin
overview; this file covers the endpoints' own contract: auth, role-based
shape, the admin-only health snapshot, and the alias behaviour.

No Redis is used (conftest sets RATE_LIMIT_BACKEND="off"), so the queue and
Redis fields are expected to report "not available" rather than numbers.
"""
import pytest

from app.models.user import UserRole

OVERVIEW = "/api/overview"
HEALTH = "/api/admin/health-metrics"
LEGACY_OVERVIEW = "/api/v1/overview"
LEGACY_HEALTH = "/api/v1/admin/health-metrics"

HEALTH_KEYS = {
    "queue_depth",
    "queues",
    "quota_window_usage",
    "stuck_rows",
    "redis_status",
    "llm_task_results",
}


# ------------------------------------------------------------ /api/overview

def test_overview_requires_login(client):
    assert client.get(OVERVIEW).status_code == 401


@pytest.mark.parametrize(
    "role, expected",
    [
        (UserRole.USER, "applicant"),
        (UserRole.RECRUITER, "recruiter"),
        (UserRole.ADMIN, "admin"),
        (UserRole.SUPERUSER, "admin"),
    ],
)
def test_overview_payload_depends_on_role(client, make_user, auth_headers, role, expected):
    user, _ = make_user(role=role)
    resp = client.get(OVERVIEW, headers=auth_headers(user))
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == expected


def test_superuser_overview_is_flagged(client, make_user, auth_headers):
    su, _ = make_user(role=UserRole.SUPERUSER)
    admin, _ = make_user(role=UserRole.ADMIN)
    assert client.get(OVERVIEW, headers=auth_headers(su)).json()["is_superuser"] is True
    assert client.get(OVERVIEW, headers=auth_headers(admin)).json()["is_superuser"] is False


# ------------------------------------------------- /api/admin/health-metrics

def test_health_metrics_requires_login(client):
    assert client.get(HEALTH).status_code == 401


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER])
def test_health_metrics_is_forbidden_for_non_admins(client, make_user, auth_headers, role):
    user, _ = make_user(role=role)
    assert client.get(HEALTH, headers=auth_headers(user)).status_code == 403


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERUSER])
def test_health_metrics_for_admins_has_the_expected_shape(client, make_user, auth_headers, role):
    user, _ = make_user(role=role)
    resp = client.get(HEALTH, headers=auth_headers(user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert HEALTH_KEYS <= set(body)
    assert isinstance(body["queues"], dict)
    assert isinstance(body["stuck_rows"], dict)
    assert isinstance(body["llm_task_results"], list)
    # the two live counters are always present, even with nothing processing
    assert body["stuck_rows"]["resume_extractions"] == 0
    assert body["stuck_rows"]["job_extractions"] == 0


def test_health_metrics_without_redis_reports_it_instead_of_failing(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    body = client.get(HEALTH, headers=auth_headers(admin)).json()
    assert body["redis_status"] == "disabled"
    assert body["queue_depth"] is None
    assert body["queues"] == {}


# ------------------------------------------------- deprecated /api/v1 aliases

def test_legacy_overview_still_works_and_is_marked_deprecated(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    h = auth_headers(admin)
    old = client.get(LEGACY_OVERVIEW, headers=h)
    new = client.get(OVERVIEW, headers=h)
    assert old.status_code == 200, old.text
    assert old.headers.get("deprecation") == "true"
    assert "deprecation" not in new.headers
    assert old.json()["role"] == new.json()["role"] == "admin"


def test_legacy_health_metrics_still_works_and_is_marked_deprecated(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    h = auth_headers(admin)
    old = client.get(LEGACY_HEALTH, headers=h)
    new = client.get(HEALTH, headers=h)
    assert old.status_code == 200, old.text
    assert old.headers.get("deprecation") == "true"
    assert "deprecation" not in new.headers
    assert HEALTH_KEYS <= set(old.json())


def test_legacy_aliases_keep_their_auth_rules(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    assert client.get(LEGACY_OVERVIEW).status_code == 401
    assert client.get(LEGACY_HEALTH).status_code == 401
    assert client.get(LEGACY_HEALTH, headers=auth_headers(recruiter)).status_code == 403


def test_legacy_users_and_jobs_aliases_still_answer(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    h = auth_headers(recruiter)
    me_new = client.get("/api/users/me", headers=h)
    me_old = client.get("/api/v1/users/me", headers=h)
    assert me_new.status_code == me_old.status_code == 200
    assert me_old.headers.get("deprecation") == "true"
    assert me_old.json()["id"] == me_new.json()["id"]
    assert client.get("/api/v1/jobs", headers=h).status_code == 200


def test_openapi_documents_only_the_canonical_prefix(client):
    paths = set(client.get("/openapi.json").json()["paths"])
    assert OVERVIEW in paths
    assert HEALTH in paths
    assert not [p for p in paths if p.startswith("/api/v1")]
