"""/api/admin/llm-config (routes/llm_config.py) and GET /api/health/llm.

llm_configs is NOT in conftest's TRUNCATE list (the migration seeds its rows,
and the app needs them), so PUTs here would leak into later tests and later
runs. The autouse fixture below snapshots the table before each test and
restores it afterwards.
"""
import pytest

from app.api.routes import llm_config as llm_routes
from app.core.llm_provider_registry import PROVIDERS, LLMConfigError
from app.models.audit_log import AuditLog
from app.models.llm_config import LLMConfig
from app.models.user import UserRole

BASE = "/api/admin/llm-config"


@pytest.fixture(autouse=True)
def _restore_llm_configs(db):
    before = [(r.id, r.task, r.provider, r.model) for r in db.query(LLMConfig).all()]
    yield
    db.rollback()
    db.query(LLMConfig).delete()
    for id_, task, provider, model in before:
        db.add(LLMConfig(id=id_, task=task, provider=provider, model=model))
    db.commit()


def _set_config(db, task, provider, model):
    row = db.query(LLMConfig).filter(LLMConfig.task == task).one()
    row.provider, row.model = provider, model
    db.commit()


def _row(db, task):
    db.expire_all()
    return db.query(LLMConfig).filter(LLMConfig.task == task).one()


class _FakeModel:
    def __init__(self, content="ok", error=None):
        self.content, self.error, self.prompts = content, error, []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return type("Reply", (), {"content": self.content})()


@pytest.fixture()
def fake_model(monkeypatch):
    """fake_model(content=..., error=...) swaps the chat model the probe route
    builds, so no test ever makes a real provider call."""
    def _install(**kwargs):
        model = _FakeModel(**kwargs)
        calls = []

        def _get(task, **overrides):
            calls.append(task)
            return model

        monkeypatch.setattr(llm_routes, "get_chat_model_for_task", _get)
        model.tasks = calls
        return model
    return _install


# ---------------------------------------------------------------------------
# Access control — every route is admin/superuser only
# ---------------------------------------------------------------------------

_ROUTES = [
    ("get", BASE, None),
    ("get", f"{BASE}/providers", None),
    ("put", f"{BASE}/resume_skills", {"provider": "groq", "model": "m"}),
    ("post", f"{BASE}/resume_skills/probe", None),
]


@pytest.mark.parametrize("method,path,body", _ROUTES)
def test_unauthenticated_gets_401(client, method, path, body):
        assert client.request(method.upper(), path, json=body).status_code == 401


@pytest.mark.parametrize("role", [UserRole.USER, UserRole.RECRUITER])
@pytest.mark.parametrize("method,path,body", _ROUTES)
def test_non_admins_get_403(client, make_user, auth_headers, db, method, path, body, role):
    user, _ = make_user(role=role)
    before = _row(db, "resume_skills")
    snapshot = (before.provider, before.model)
    resp = client.request(method.upper(), path, json=body, headers=auth_headers(user))
    assert resp.status_code == 403
    after = _row(db, "resume_skills")
    assert (after.provider, after.model) == snapshot


def test_forbidden_probe_never_reaches_the_provider(client, make_user, auth_headers, fake_model):
    model = fake_model()
    user, _ = make_user(role=UserRole.RECRUITER)
    client.post(f"{BASE}/resume_skills/probe", headers=auth_headers(user))
    assert model.tasks == [] and model.prompts == []


def test_inactive_admin_is_refused(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN, is_active=False)
    assert client.get(BASE, headers=auth_headers(admin)).status_code == 403


# ---------------------------------------------------------------------------
# GET /api/admin/llm-config and /providers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERUSER])
def test_list_returns_every_task_ordered_by_task(client, make_user, auth_headers, role):
    actor, _ = make_user(role=role)
    resp = client.get(BASE, headers=auth_headers(actor))
    assert resp.status_code == 200
    rows = resp.json()
    tasks = [r["task"] for r in rows]
    assert {"resume_skills", "jd_skills"} <= set(tasks)
    assert tasks == sorted(tasks)
    assert all(set(r) == {"task", "provider", "model"} for r in rows)


def test_list_reflects_a_changed_row(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.ADMIN)
    _set_config(db, "jd_skills", "openai", "gpt-test")
    rows = {r["task"]: r for r in client.get(BASE, headers=auth_headers(admin)).json()}
    assert rows["jd_skills"]["provider"] == "openai"
    assert rows["jd_skills"]["model"] == "gpt-test"


def test_providers_lists_the_registry_sorted(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.get(f"{BASE}/providers", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert resp.json() == sorted(PROVIDERS)
    assert "unset" not in resp.json()


# ---------------------------------------------------------------------------
# PUT /api/admin/llm-config/{task}
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.SUPERUSER])
def test_put_updates_provider_and_model(client, make_user, auth_headers, db, role):
    actor, _ = make_user(role=role)
    resp = client.put(
        f"{BASE}/resume_skills",
        json={"provider": "groq", "model": "llama-test"},
        headers=auth_headers(actor),
    )
    assert resp.status_code == 200
    assert resp.json() == {"task": "resume_skills", "provider": "groq", "model": "llama-test"}
    row = _row(db, "resume_skills")
    assert (row.provider, row.model) == ("groq", "llama-test")


def test_put_only_touches_the_named_task(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.ADMIN)
    other = _row(db, "jd_skills")
    other_before = (other.provider, other.model)
    client.put(
        f"{BASE}/resume_skills",
        json={"provider": "openai", "model": "gpt-test"},
        headers=auth_headers(admin),
    )
    other = _row(db, "jd_skills")
    assert (other.provider, other.model) == other_before


def test_put_writes_an_audit_entry_with_before_and_after(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.ADMIN)
    _set_config(db, "resume_skills", "openai", "old-model")
    client.put(
        f"{BASE}/resume_skills",
        json={"provider": "groq", "model": "new-model"},
        headers=auth_headers(admin),
    )
    db.expire_all()
    entries = db.query(AuditLog).filter(AuditLog.resource_type == "llm_config").all()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.action == "update"
    assert entry.actor_id == admin.id and entry.actor_email == admin.email
    assert (entry.before["provider"], entry.before["model"]) == ("openai", "old-model")
    assert (entry.after["provider"], entry.after["model"]) == ("groq", "new-model")


def test_put_unknown_task_is_404_and_writes_nothing(client, make_user, auth_headers, db):
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.put(
        f"{BASE}/no_such_task",
        json={"provider": "groq", "model": "m"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 404
    assert db.query(AuditLog).filter(AuditLog.resource_type == "llm_config").count() == 0


@pytest.mark.parametrize("provider", ["not-a-provider", "unset", "", "GROQ"])
def test_put_rejects_unregistered_provider_and_leaves_row_alone(
    client, make_user, auth_headers, db, provider
):
    admin, _ = make_user(role=UserRole.ADMIN)
    _set_config(db, "resume_skills", "groq", "keep-me")
    resp = client.put(
        f"{BASE}/resume_skills",
        json={"provider": provider, "model": "m"},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 422
    row = _row(db, "resume_skills")
    assert (row.provider, row.model) == ("groq", "keep-me")
    assert db.query(AuditLog).filter(AuditLog.resource_type == "llm_config").count() == 0


def test_put_422_message_lists_available_providers(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.put(
        f"{BASE}/resume_skills",
        json={"provider": "nope", "model": "m"},
        headers=auth_headers(admin),
    )
    assert "groq" in resp.text and "openai" in resp.text


@pytest.mark.parametrize("body", [{}, {"provider": "groq"}, {"model": "m"}])
def test_put_requires_both_fields(client, make_user, auth_headers, body):
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.put(f"{BASE}/resume_skills", json=body, headers=auth_headers(admin))
    assert resp.status_code == 422


@pytest.mark.xfail(
    strict=True,
    reason="LLMConfigUpdate.model has no min_length, so a blank model is accepted. "
    "Remove this marker once the schema rejects it.",
)
def test_put_rejects_blank_model(client, make_user, auth_headers):
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.put(
        f"{BASE}/resume_skills",
        json={"provider": "groq", "model": "   "},
        headers=auth_headers(admin),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/admin/llm-config/{task}/probe
# ---------------------------------------------------------------------------

def test_probe_success_reports_reply_and_timing(client, make_user, auth_headers, fake_model):
    model = fake_model(content="ok")
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.post(f"{BASE}/jd_skills/probe", headers=auth_headers(admin))
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["reply"] == "ok"
    assert isinstance(body["elapsed_s"], (int, float)) and body["elapsed_s"] >= 0
    assert model.tasks == ["jd_skills"]
    assert len(model.prompts) == 1


def test_probe_truncates_long_replies_to_80_chars(client, make_user, auth_headers, fake_model):
    fake_model(content="x" * 500)
    admin, _ = make_user(role=UserRole.SUPERUSER)
    body = client.post(f"{BASE}/resume_skills/probe", headers=auth_headers(admin)).json()
    assert len(body["reply"]) == 80


def test_probe_config_error_is_reported_not_raised(client, make_user, auth_headers, fake_model):
    fake_model(error=LLMConfigError("GROQ_API_KEY is not set"))
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.post(f"{BASE}/resume_skills/probe", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "stage": "config", "error": "GROQ_API_KEY is not set"}


def test_probe_provider_failure_is_reported_not_raised(client, make_user, auth_headers, fake_model):
    fake_model(error=RuntimeError("rate limited"))
    admin, _ = make_user(role=UserRole.ADMIN)
    resp = client.post(f"{BASE}/resume_skills/probe", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert resp.json() == {
        "ok": False,
        "stage": "provider_call",
        "error": "RuntimeError: rate limited",
    }


def test_probe_changes_nothing_and_writes_no_audit(client, make_user, auth_headers, fake_model, db):
    fake_model()
    admin, _ = make_user(role=UserRole.ADMIN)
    _set_config(db, "resume_skills", "groq", "stay")
    client.post(f"{BASE}/resume_skills/probe", headers=auth_headers(admin))
    row = _row(db, "resume_skills")
    assert (row.provider, row.model) == ("groq", "stay")
    assert db.query(AuditLog).filter(AuditLog.resource_type == "llm_config").count() == 0


# ---------------------------------------------------------------------------
# GET /api/health/llm (public, read-only)
# ---------------------------------------------------------------------------

def test_health_llm_ok_when_every_task_is_configured(client, db):
    for task in ("resume_skills", "jd_skills"):
        _set_config(db, task, "groq", "m")
    resp = client.get("/api/health/llm")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "unset_tasks" not in body
    assert {c["task"] for c in body["configs"]} >= {"resume_skills", "jd_skills"}


def test_health_llm_flags_only_the_unset_tasks(client, db):
    _set_config(db, "resume_skills", "groq", "m")
    _set_config(db, "jd_skills", "unset", "unset")
    body = client.get("/api/health/llm").json()
    assert body["status"] == "error"
    assert body["unset_tasks"] == ["jd_skills"]


def test_health_llm_flags_a_task_with_only_the_model_unset(client, db):
    _set_config(db, "resume_skills", "groq", "unset")
    _set_config(db, "jd_skills", "groq", "m")
    body = client.get("/api/health/llm").json()
    assert body["status"] == "error"
    assert body["unset_tasks"] == ["resume_skills"]


def test_health_llm_reports_missing_rows(client, db):
    db.query(LLMConfig).delete()
    db.commit()
    body = client.get("/api/health/llm").json()
    assert body["status"] == "error"
    assert "run migrations" in body["detail"]