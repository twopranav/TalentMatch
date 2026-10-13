"""
Large-upload and bulk-upload behaviour through the real API:

- a resume exactly at the size limit is accepted, one byte over is not;
- a realistically big (image-heavy) PDF round-trips intact;
- bulk uploads store files in parallel (capped), keep result order, isolate
  per-file storage / DB failures, and leave no orphaned blobs;
- the recruiter bulk-apply endpoint handles a big batch end to end.
"""
import io
import os
import threading
import time

import pytest

from app.api.routes import resumes as resumes_routes
from app.core.config import settings
from app.models.user import UserRole

LIMIT = 10 * 1024 * 1024  # resumes._MAX_RESUME_UPLOAD_BYTES
PDF = "application/pdf"


def _stored_files() -> list:
    root = settings.LOCAL_STORAGE_ROOT  # conftest points this at a per-test tmp dir
    return [os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs]


def _pad_to(pdf: bytes, size: int) -> bytes:
    """PDF readers ignore trailing whitespace after %%EOF, so this is still
    a valid PDF, just exactly `size` bytes."""
    assert len(pdf) <= size
    return pdf + b"\n" * (size - len(pdf))


# ---------------------------------------------------------------------------
# Size limit boundary
# ---------------------------------------------------------------------------

def test_resume_exactly_at_the_size_limit_is_accepted(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    content = _pad_to(pdf_bytes("at the limit"), LIMIT)
    assert len(content) == LIMIT

    resp = client.post(
        "/api/resumes", files={"file": ("big.pdf", content, PDF)}, headers=auth_headers(candidate),
    )

    assert resp.status_code == 201
    assert resp.json()["size_bytes"] == LIMIT


def test_resume_one_byte_over_the_size_limit_is_rejected(client, make_user, auth_headers, pdf_bytes):
    candidate, _ = make_user(role=UserRole.USER)
    content = _pad_to(pdf_bytes("over"), LIMIT + 1)

    resp = client.post(
        "/api/resumes", files={"file": ("big.pdf", content, PDF)}, headers=auth_headers(candidate),
    )

    assert resp.status_code == 413
    assert _stored_files() == []


def test_large_image_heavy_pdf_round_trips_intact(client, make_user, auth_headers):
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    side = 1500  # ~6.4 MB of incompressible pixels
    img = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 780, "SKILLS")
    c.drawImage(ImageReader(img), 50, 100, width=400, height=400)
    c.save()
    content = buf.getvalue()
    assert 5 * 1024 * 1024 < len(content) < LIMIT

    candidate, _ = make_user(role=UserRole.USER)
    headers = auth_headers(candidate)
    created = client.post("/api/resumes", files={"file": ("scan.pdf", content, PDF)}, headers=headers)
    assert created.status_code == 201

    downloaded = client.get(f"/api/resumes/{created.json()['id']}/file", headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == content


# ---------------------------------------------------------------------------
# Bulk upload: parallel, ordered, isolated
# ---------------------------------------------------------------------------

@pytest.fixture
def slow_storage(monkeypatch):
    """Wraps the real (local-disk) upload with a delay and records how many
    uploads were in flight at once."""
    real = resumes_routes.upload_resume_blob
    lock = threading.Lock()
    state = {"now": 0, "peak": 0}

    def slow(contents, blob_name, content_type):
        with lock:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        try:
            time.sleep(0.15)
            return real(contents, blob_name, content_type)
        finally:
            with lock:
                state["now"] -= 1

    monkeypatch.setattr(resumes_routes, "upload_resume_blob", slow)
    return state


def test_bulk_upload_stores_in_parallel_in_order_and_across_chunks(
    client, make_user, auth_headers, pdf_bytes, slow_storage, dispatched,
):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    count = settings.BULK_CHUNK_SIZE + 8  # forces more than one chunk
    names = [f"r{i:03d}.pdf" for i in range(count)]
    files = [("files", (n, pdf_bytes(n), PDF)) for n in names]

    started = time.perf_counter()
    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(recruiter))
    elapsed = time.perf_counter() - started

    assert resp.status_code == 200
    results = resp.json()
    assert [r["original_filename"] for r in results] == names  # input order kept
    assert all(r["success"] for r in results)
    assert 1 < slow_storage["peak"] <= settings.BULK_UPLOAD_CONCURRENCY
    assert elapsed < count * 0.15  # one-by-one would take at least this long
    assert dispatched["resume"] == [r["resume"]["id"] for r in results]
    assert len(_stored_files()) == count


def test_bulk_upload_storage_failure_hits_one_file_and_leaks_nothing(
    client, make_user, auth_headers, pdf_bytes, monkeypatch, dispatched,
):
    real = resumes_routes.upload_resume_blob
    lock = threading.Lock()
    calls = {"n": 0}

    def flaky(contents, blob_name, content_type):
        with lock:
            calls["n"] += 1
            n = calls["n"]
        if n == 2:
            raise RuntimeError("down: https://acct.blob.core.windows.net/c?sig=SECRET")
        return real(contents, blob_name, content_type)

    monkeypatch.setattr(resumes_routes, "upload_resume_blob", flaky)
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    files = [("files", (f"r{i}.pdf", pdf_bytes(f"r{i}"), PDF)) for i in range(5)]

    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(recruiter))

    assert resp.status_code == 200
    results = resp.json()
    failed = [r for r in results if not r["success"]]
    ok = [r for r in results if r["success"]]
    assert len(failed) == 1 and len(ok) == 4
    assert "Failed to store" in failed[0]["error"]
    assert "SECRET" not in failed[0]["error"] and "blob.core" not in failed[0]["error"]  # no storage details leak
    assert len(client.get("/api/resumes", headers=auth_headers(recruiter)).json()) == 4
    assert len(_stored_files()) == 4
    assert dispatched["resume"] == [r["resume"]["id"] for r in ok]


def test_bulk_upload_db_failure_for_one_file_removes_its_blob(
    client, make_user, auth_headers, pdf_bytes, monkeypatch,
):
    real = resumes_routes._make_resume_row
    calls = {"n": 0}

    def flaky_row(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("insert failed")
        return real(*args, **kwargs)

    monkeypatch.setattr(resumes_routes, "_make_resume_row", flaky_row)
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    files = [("files", (f"r{i}.pdf", pdf_bytes(f"r{i}"), PDF)) for i in range(4)]

    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(recruiter))

    results = resp.json()
    assert [r["success"] for r in results] == [True, False, True, True]
    assert results[1]["error"] == "Could not save this file."
    assert len(client.get("/api/resumes", headers=auth_headers(recruiter)).json()) == 3
    assert len(_stored_files()) == 3  # the failed file's blob was cleaned up


def test_bulk_upload_mixes_bad_oversized_and_good_files(client, make_user, auth_headers, pdf_bytes):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    files = [
        ("files", ("good1.pdf", pdf_bytes("one"), PDF)),
        ("files", ("huge.pdf", _pad_to(pdf_bytes("x"), LIMIT + 1), PDF)),
        ("files", ("fake.pdf", b"not a pdf at all", PDF)),
        ("files", ("note.txt", b"hello", "text/plain")),
        ("files", ("good2.pdf", pdf_bytes("two"), PDF)),
    ]

    resp = client.post("/api/resumes/bulk", files=files, headers=auth_headers(recruiter))

    assert resp.status_code == 200
    by_name = {r["original_filename"]: r for r in resp.json()}
    assert by_name["good1.pdf"]["success"] and by_name["good2.pdf"]["success"]
    assert not by_name["huge.pdf"]["success"] and "10 MB" in by_name["huge.pdf"]["error"]
    assert not by_name["fake.pdf"]["success"] and "do not match" in by_name["fake.pdf"]["error"]
    assert not by_name["note.txt"]["success"] and "PDF or DOCX" in by_name["note.txt"]["error"]
    assert len(_stored_files()) == 2


# ---------------------------------------------------------------------------
# Recruiter bulk upload + apply, at scale
# ---------------------------------------------------------------------------

def _published_job(client, auth_headers, recruiter, pdf_bytes):
    job_id = client.post(
        "/api/jobs", json={"title": "Job", "description": "Do the work"}, headers=auth_headers(recruiter),
    ).json()["id"]
    client.post(
        f"/api/jobs/{job_id}/jd", files={"file": ("jd.pdf", pdf_bytes("JD text"), PDF)},
        headers=auth_headers(recruiter),
    )
    client.patch(f"/api/jobs/{job_id}", json={"status": "published"}, headers=auth_headers(recruiter))
    return job_id


def test_bulk_upload_and_apply_handles_a_big_batch(
    client, make_user, auth_headers, pdf_bytes, slow_storage, dispatched,
):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    dispatched["resume"].clear()  # the JD upload queued its own extraction
    count = 40
    files = [("files", (f"c{i:03d}.pdf", pdf_bytes(f"candidate {i}"), PDF)) for i in range(count)]

    resp = client.post(
        f"/api/applications/job/{job_id}/bulk-upload", files=files, headers=auth_headers(recruiter),
    )

    assert resp.status_code == 200
    results = resp.json()
    assert [r["original_filename"] for r in results] == [f"c{i:03d}.pdf" for i in range(count)]
    assert all(r["success"] for r in results)
    assert len({r["application_id"] for r in results}) == count
    assert slow_storage["peak"] > 1
    assert len(dispatched["resume"]) == count
    applicants = client.get(f"/api/applications/job/{job_id}", headers=auth_headers(recruiter)).json()
    assert len(applicants) == count
    assert len(_stored_files()) == count + 1  # + the JD file


def test_bulk_upload_and_apply_failures_leave_no_orphans(
    client, make_user, auth_headers, pdf_bytes, monkeypatch,
):
    from app.api.routes import applications as applications_routes

    real = applications_routes._add_unowned_application
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("application insert failed")
        return real(*args, **kwargs)

    monkeypatch.setattr(applications_routes, "_add_unowned_application", flaky)
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    job_id = _published_job(client, auth_headers, recruiter, pdf_bytes)
    files = [("files", (f"c{i}.pdf", pdf_bytes(f"c{i}"), PDF)) for i in range(5)]

    resp = client.post(
        f"/api/applications/job/{job_id}/bulk-upload", files=files, headers=auth_headers(recruiter),
    )

    results = resp.json()
    assert [r["success"] for r in results] == [True, True, False, True, True]
    assert results[2]["error"] == "Could not apply this file."
    assert len(client.get("/api/resumes", headers=auth_headers(recruiter)).json()) == 4
    assert len(_stored_files()) == 4 + 1  # four resumes + the JD file
