import pytest

from app.core import rate_limit
from app.core.config import Settings, settings
from app.core.upload_safety import content_disposition, safe_extension
from app.models.user import UserRole

DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_resume_with_wrong_bytes_is_rejected(client, make_user, auth_headers):
    candidate, _ = make_user(role=UserRole.USER)
    files = {"file": ("evil.pdf", b"MZ\x90\x00 this is an exe", "application/pdf")}
    resp = client.post("/api/resumes", files=files, headers=auth_headers(candidate))
    assert resp.status_code == 415


def test_docx_that_is_not_a_docx_is_rejected(client, make_user, auth_headers):
    candidate, _ = make_user(role=UserRole.USER)
    files = {"file": ("fake.docx", b"PK\x03\x04 not really a zip", DOCX_TYPE)}
    resp = client.post("/api/resumes", files=files, headers=auth_headers(candidate))
    assert resp.status_code == 415


def test_jd_with_wrong_bytes_is_rejected(client, make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job = client.post("/api/jobs", json={"title": "Dev", "description": "x"}, headers=auth_headers(recruiter)).json()
    files = {"file": ("jd.pdf", b"not a pdf at all", "application/pdf")}
    resp = client.post(f"/api/jobs/{job['id']}/jd", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 415


def test_avatar_with_wrong_bytes_is_rejected(client, make_user, auth_headers):
    user, _ = make_user()
    files = {"file": ("me.png", b"definitely not a png", "image/png")}
    resp = client.post("/api/users/me/avatar", files=files, headers=auth_headers(user))
    assert resp.status_code == 415


def test_bulk_upload_file_count_is_capped(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    one = pdf_bytes("x")
    files = [("files", (f"r{i}.pdf", one, "application/pdf")) for i in range(51)]
    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(recruiter))
    assert resp.status_code == 413


def test_stored_extension_ignores_client_filename():
    assert safe_extension("payload.exe", "application/pdf") == ".pdf"
    assert safe_extension("x.../../../etc", None) == ""


def test_content_disposition_cannot_be_broken_out_of():
    header = content_disposition('evil"\r\nX-Injected: 1.pdf')
    assert "\r" not in header and "\n" not in header
    assert header.count('"') == 2  # only the ascii-fallback delimiters


def test_download_sets_nosniff(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    headers = auth_headers(candidate)
    rid = client.post(
        "/api/resumes", files={"file": ("r.pdf", pdf_bytes("r"), "application/pdf")}, headers=headers
    ).json()["id"]
    resp = client.get(f"/api/resumes/{rid}/file", headers=headers)
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "filename*=UTF-8''" in resp.headers["content-disposition"]


def test_oversized_body_rejected_before_parsing(client):
    resp = client.post("/api/auth/login", content=b"x" * (13 * 1024 * 1024))
    assert resp.status_code == 413


def test_login_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "memory")
    codes = [
        client.post("/api/auth/login", data={"username": f"u{i}@x.com", "password": "nope"}).status_code
        for i in range(21)
    ]
    assert codes[:20] == [401] * 20
    assert codes[20] == 429


def test_register_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "memory")
    codes = [
        client.post("/api/auth/register", json={"email": f"n{i}@x.com", "password": "abcdefg1"}).status_code
        for i in range(11)
    ]
    assert codes[-1] == 429


def test_login_lockout_ignores_email_case(client, make_user, monkeypatch):
    user, password = make_user(email="mixed@test.com")
    for _ in range(5):
        client.post("/api/auth/login", data={"username": "MiXeD@Test.com", "password": "wrong"})
    resp = client.post("/api/auth/login", data={"username": "mixed@test.com", "password": password})
    assert resp.status_code == 429


def test_security_headers_present(client):
    resp = client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "SAMEORIGIN"


def test_cors_rejects_unlisted_method_header(client):
    resp = client.options(
        "/api/jobs",
        headers={
            "Origin": settings.CORS_ORIGINS[0],
            "Access-Control-Request-Method": "TRACE",
            "Access-Control-Request-Headers": "X-Evil",
        },
    )
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "kwargs",
    [
        {"DEBUG": True, "JWT_SECRET_KEY": "x" * 40},
        {"DEBUG": False, "JWT_SECRET_KEY": "short"},
        {"DEBUG": False, "JWT_SECRET_KEY": "x" * 40, "CORS_ORIGINS": ["*"]},
    ],
)
def test_production_refuses_unsafe_settings(kwargs):
    with pytest.raises(ValueError):
        Settings(ENV="production", **kwargs)


def test_production_accepts_safe_settings():
    s = Settings(ENV="production", DEBUG=False, JWT_SECRET_KEY="x" * 40, CORS_ORIGINS=["https://app.example.com"])
    assert s.IS_PRODUCTION