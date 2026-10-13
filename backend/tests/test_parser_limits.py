"""
Large / hostile-file behaviour of the resume parser and extraction task:

- a PDF with far more pages than any resume is only read up to
  MAX_RESUME_PDF_PAGES;
- an image-only (scanned) PDF fails cleanly instead of crashing;
- a big, image-heavy PDF near the upload limit still parses;
- a task that runs out of time is marked FAILED, not retried.

Pure: no database, Redis or LLM, so the conftest DB fixtures are
overridden with no-ops (same as test_resume_skills_task.py).
"""
import io
import os
import time
from types import SimpleNamespace

import pytest

from app.core import skills_pdf_locator
from app.core.skills_pdf_locator import MAX_RESUME_PDF_PAGES, locate_resume_sections
from app.core.text_extract import EmptyExtractionError, extract_text_from_bytes
from app.models.resume import ResumeExtractionStatus


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield


def _text_pdf(pages: int) -> bytes:
    """`pages` pages; the Skills section is on page 1."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for n in range(pages):
        y = 780
        if n == 0:
            for line in ("Jane Doe", "SKILLS", "Python, SQL, Docker", "EXPERIENCE", "Acme - Engineer"):
                c.drawString(50, y, line)
                y -= 18
        for i in range(30):
            c.drawString(50, y, f"Page {n + 1} filler line {i} with some ordinary words in it.")
            y -= 18
        c.showPage()
    c.save()
    return buf.getvalue()


def _scanned_pdf() -> bytes:
    """A page that is only a picture: no text layer at all."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    img = Image.new("RGB", (600, 800), "white")
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawImage(ImageReader(img), 0, 0, width=595, height=842)
    c.save()
    return buf.getvalue()


def _image_heavy_pdf(megabytes: float = 7.0) -> bytes:
    """A resume page plus an incompressible picture, to make the file big."""
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    side = int((megabytes * 1024 * 1024 / 3) ** 0.5)
    img = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i, line in enumerate(("Jane Doe", "SKILLS", "Python, SQL, Docker", "EDUCATION", "BSc")):
        c.drawString(50, 780 - 18 * i, line)
    c.drawImage(ImageReader(img), 50, 100, width=400, height=400)
    c.save()
    return buf.getvalue()


@pytest.fixture
def counted_pages(monkeypatch):
    """Counts how many pages the locator actually lays out."""
    seen = {"n": 0}
    real = skills_pdf_locator._extract_visual_segments

    def counting(page):
        seen["n"] += 1
        return real(page)

    monkeypatch.setattr(skills_pdf_locator, "_extract_visual_segments", counting)
    return seen


def test_pdf_over_the_page_cap_is_only_read_up_to_the_cap(counted_pages):
    pdf = _text_pdf(MAX_RESUME_PDF_PAGES * 6)

    located = locate_resume_sections(pdf, "huge.pdf")

    assert counted_pages["n"] == MAX_RESUME_PDF_PAGES
    # The cap truncates; it doesn't break locating what's on the early pages.
    assert located["skills"]["found"] is True
    assert "python" in located["skills"]["section_text"].lower()


def test_pdf_under_the_page_cap_is_read_in_full(counted_pages):
    locate_resume_sections(_text_pdf(3), "short.pdf")

    assert counted_pages["n"] == 3


def test_pdf_exactly_at_the_page_cap_is_read_in_full(counted_pages):
    locate_resume_sections(_text_pdf(MAX_RESUME_PDF_PAGES), "edge.pdf")

    assert counted_pages["n"] == MAX_RESUME_PDF_PAGES


def test_scanned_pdf_has_no_extractable_text():
    with pytest.raises(EmptyExtractionError):
        extract_text_from_bytes(_scanned_pdf(), "scan.pdf")


def test_scanned_pdf_locates_nothing_but_does_not_crash():
    located = locate_resume_sections(_scanned_pdf(), "scan.pdf")

    assert located["skills"]["found"] is False
    assert not located["skills"]["section_text"]


def test_big_image_heavy_pdf_near_the_upload_limit_still_parses():
    pdf = _image_heavy_pdf(7.0)
    assert 5 * 1024 * 1024 < len(pdf) < 10 * 1024 * 1024  # a realistic "large" upload

    started = time.perf_counter()
    located = locate_resume_sections(pdf, "big.pdf")
    elapsed = time.perf_counter() - started

    assert located["skills"]["found"] is True
    assert "python" in located["skills"]["section_text"].lower()
    assert elapsed < 30  # generous: guards against decoding the image per word


def test_pdf_page_cap_is_sane():
    assert 3 <= MAX_RESUME_PDF_PAGES <= 30


# ---------------------------------------------------------------------
# Celery time limits
# ---------------------------------------------------------------------


def test_extraction_tasks_have_time_limits_configured():
    from app.core.celery_app import celery_app
    from app.core.config import settings

    for name in ("skills_extraction.run", "jd_skills_extraction.run"):
        ann = celery_app.conf.task_annotations[name]
        assert ann["soft_time_limit"] == settings.EXTRACTION_SOFT_TIME_LIMIT
        assert ann["time_limit"] == settings.EXTRACTION_HARD_TIME_LIMIT
        assert ann["time_limit"] > ann["soft_time_limit"]


class _FakeDB:
    def __init__(self, row):
        self.row = row

    def get(self, _model, _id):
        return self.row

    def commit(self):
        pass

    def close(self):
        pass


def test_resume_task_that_hits_the_soft_limit_fails_cleanly_without_retry(monkeypatch):
    from celery.exceptions import SoftTimeLimitExceeded

    from app.core import skills_extraction_tasks as tasks

    resume = SimpleNamespace(
        id="resume-1", blob_path="x/y.pdf", original_filename="y.pdf",
        skills_result=None, skills_by_source=None, skills_section_heading=None,
        skills_extraction_status=ResumeExtractionStatus.PENDING,
        skills_extraction_error=None, skills_extracted_at=None,
    )
    monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeDB(resume))
    monkeypatch.setattr(tasks, "download_resume_blob", lambda path: b"%PDF-")
    monkeypatch.setattr(tasks, "_store_experience", lambda r, b: None)

    def too_slow(raw, filename):
        raise SoftTimeLimitExceeded()

    monkeypatch.setattr(tasks, "locate_resume_sections", too_slow)
    llm_called = []
    monkeypatch.setattr(tasks, "extract_skills_by_source", lambda b: llm_called.append(1))
    rescored = []
    monkeypatch.setattr(tasks, "safe_dispatch_for_resume", lambda db, rid: rescored.append(rid))

    tasks.run_skills_extraction_task.run("resume-1")  # a retry would raise here

    assert resume.skills_extraction_status == ResumeExtractionStatus.FAILED
    assert "too long" in resume.skills_extraction_error
    assert not llm_called
    assert rescored == ["resume-1"]  # applications get marked, not left pending
