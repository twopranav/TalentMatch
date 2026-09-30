"""
Tests for the resume skills-extraction Celery task
(app/core/skills_extraction_tasks.py): stored file -> locate skills
section -> clean -> LLM -> validate -> persist.

Mirrors the JD-side task tests in test_jd_locator.py. The LLM, blob
storage and DB session are faked; the section locator, text prep and
postprocess_skills run for real. No database, Redis or LLM is touched, so
the session/function DB fixtures from conftest.py are overridden with
no-ops below.
"""

import io
from types import SimpleNamespace

import pytest

from app.models.resume import ResumeExtractionStatus


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    """Override conftest's DB bootstrap: these tests are pure."""
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """Override conftest's per-test TRUNCATE: these tests never touch the DB."""
    yield


def _resume_pdf(lines: list[str]) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    y = 780
    for line in lines:
        c.drawString(50, y, line)
        y -= 18
    c.save()
    return buf.getvalue()


RESUME_WITH_SKILLS = [
    "Jane Doe",
    "Senior Backend Engineer",
    "EXPERIENCE",
    "Acme Corp - Backend Engineer",
    "Built internal services.",
    "SKILLS",
    "Python, SQL, Docker",
    "Kubernetes",
    "EDUCATION",
    "BSc Computer Science",
]

RESUME_WITHOUT_SKILLS = [
    "Jane Doe",
    "EXPERIENCE",
    "Acme Corp - Backend Engineer",
    "Built internal services for several years across teams.",
    "EDUCATION",
    "BSc Computer Science",
]


class _FakeDB:
    def __init__(self, resume):
        self._resume = resume
        self.commits = 0

    def get(self, _model, _id):
        return self._resume

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def _fake_resume(**overrides):
    fields = dict(
        blob_path="owner/abc.pdf",
        original_filename="resume.pdf",
        skills_result=None,
        skills_section_heading=None,
        skills_extraction_status=ResumeExtractionStatus.PENDING,
        skills_extraction_error=None,
        skills_extracted_at=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.fixture
def task_env(monkeypatch):
    from app.core import skills_extraction_tasks as tasks

    seen = {}

    def install(resume, blob_bytes=b"", llm=None):
        monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeDB(resume))
        monkeypatch.setattr(tasks, "download_resume_blob", lambda path: blob_bytes)

        def fake_llm(prepared_text):
            seen["llm_input"] = prepared_text
            return llm(prepared_text) if llm else []

        monkeypatch.setattr(tasks, "extract_skills_only", fake_llm)
        return tasks, seen

    return install


def test_task_reaches_llm_with_only_the_skills_section_and_marks_done(task_env):
    resume = _fake_resume()
    tasks, seen = task_env(
        resume,
        _resume_pdf(RESUME_WITH_SKILLS),
        llm=lambda text: ["python", "sql", "docker", "kubernetes"],
    )

    tasks.run_skills_extraction_task.run("resume-1")

    assert "python" in seen["llm_input"]
    assert "built internal services" not in seen["llm_input"]
    assert "computer science" not in seen["llm_input"]
    assert resume.skills_extraction_status == ResumeExtractionStatus.DONE
    assert resume.skills_result == ["python", "sql", "docker", "kubernetes"]
    assert resume.skills_extraction_error is None
    assert resume.skills_extracted_at is not None


def test_task_drops_skills_the_llm_invented(task_env):
    resume = _fake_resume()
    tasks, _ = task_env(
        resume, _resume_pdf(RESUME_WITH_SKILLS), llm=lambda text: ["python", "cobol"]
    )

    tasks.run_skills_extraction_task.run("resume-1")

    assert resume.skills_result == ["python"]


def test_task_marks_failed_when_no_skills_section(task_env):
    resume = _fake_resume()
    tasks, seen = task_env(resume, _resume_pdf(RESUME_WITHOUT_SKILLS))

    tasks.run_skills_extraction_task.run("resume-1")

    assert resume.skills_extraction_status == ResumeExtractionStatus.FAILED
    assert "skills section" in resume.skills_extraction_error
    assert "llm_input" not in seen  # the LLM is never called


def test_task_marks_failed_on_unsupported_file_type(task_env):
    resume = _fake_resume(original_filename="resume.xyz")
    tasks, _ = task_env(resume, b"hello")

    tasks.run_skills_extraction_task.run("resume-1")

    assert resume.skills_extraction_status == ResumeExtractionStatus.FAILED


def test_task_marks_failed_when_llm_raises_extraction_error(task_env):
    from app.core.skills_llm_extract import SkillsExtractionError

    def boom(_text):
        raise SkillsExtractionError("model returned junk")

    resume = _fake_resume()
    tasks, _ = task_env(resume, _resume_pdf(RESUME_WITH_SKILLS), llm=boom)

    tasks.run_skills_extraction_task.run("resume-1")

    assert resume.skills_extraction_status == ResumeExtractionStatus.FAILED
    assert "model returned junk" in resume.skills_extraction_error


def test_task_ignores_a_deleted_resume(task_env):
    tasks, seen = task_env(None)

    tasks.run_skills_extraction_task.run("resume-1")  # must not raise

    assert "llm_input" not in seen