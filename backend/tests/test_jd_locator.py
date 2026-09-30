"""
Tests for the JD required-skills locator and its Celery-task wiring.

No database, Redis, or LLM is touched. tests/conftest.py has a session
autouse fixture that builds a Postgres test DB; it is overridden below
with a no-op so this module runs on a machine with no database.

PDF layouts are generated on the fly with reportlab (skipped if it isn't
installed) so no binary fixtures live in the repo.
"""

import io
from types import SimpleNamespace

import pytest

from app.core.jd_skills_locator import (
    is_section_boundary,
    locate_jd_requirements,
    locate_required_skills,
    split_embedded_section_boundary,
)


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    """Override conftest's DB bootstrap: these tests are pure."""
    yield


# ---------------------------------------------------------------------
# Synthetic PDF builders
# ---------------------------------------------------------------------


def _build_pdf(pages: list[list[tuple[float, list[tuple[str, str]]]]]) -> bytes:
    """pages -> columns -> (x, [(kind, text), ...]); kind 'h' = heading,
    'p' = body line."""
    canvas_mod = pytest.importorskip("reportlab.pdfgen.canvas")
    pagesizes = pytest.importorskip("reportlab.lib.pagesizes")

    _, height = pagesizes.A4
    buffer = io.BytesIO()
    pdf = canvas_mod.Canvas(buffer, pagesize=pagesizes.A4)

    for page in pages:
        for x, items in page:
            y = height - 60

            for kind, text in items:
                if kind == "h":
                    pdf.setFont("Helvetica-Bold", 13)
                    y -= 8
                else:
                    pdf.setFont("Helvetica", 10)

                pdf.drawString(x, y, text)
                y -= 16

        pdf.showPage()

    pdf.save()
    return buffer.getvalue()


def _lines(section_text: str) -> list[str]:
    return [line for line in section_text.split("\n") if line.strip()]


REQS = [
    ("h", "Requirements"),
    ("p", "- 3+ years Python"),
    ("p", "- SQL and PostgreSQL"),
    ("p", "- Docker, Kubernetes"),
    ("p", "- AWS"),
]


# ---------------------------------------------------------------------
# PDF: column-aware path
# ---------------------------------------------------------------------


def test_pdf_single_column_stops_at_next_section():
    raw = _build_pdf(
        [
            [
                (
                    50,
                    [("h", "About the Role"), ("p", "We build a hiring platform.")]
                    + REQS
                    + [("h", "Nice to Have"), ("p", "- Go"), ("h", "Benefits")],
                )
            ]
        ]
    )

    result = locate_jd_requirements(raw, "jd.pdf")

    assert result["found"] is True
    assert result["heading"] == "Requirements"
    assert _lines(result["section_text"]) == [
        "- 3+ years python",
        "- sql and postgresql",
        "- docker, kubernetes",
        "- aws",
    ]


def test_pdf_does_not_sweep_in_nice_to_have():
    raw = _build_pdf([[(50, REQS + [("h", "Nice to Have"), ("p", "- Rust")])]])

    text = locate_jd_requirements(raw, "jd.pdf")["section_text"]

    assert "rust" not in text


def test_pdf_two_columns_right_column_is_unrelated_block():
    left = (
        [("h", "About the Role")]
        + [("p", "We build things.")] * 3
        + REQS
        + [("p", "- REST API design"), ("p", "- Git")]
    )
    right = [("h", "Benefits")] + [("p", "- Health cover"), ("p", "- Remote")] * 3

    result = locate_jd_requirements(_build_pdf([[(50, left), (330, right)]]), "jd.pdf")
    text = result["section_text"]

    assert result["found"] is True
    assert "rest api design" in text and "- git" in text
    assert "health cover" not in text and "remote" not in text


def test_pdf_two_columns_heading_in_right_column():
    left = [("h", "About Us")] + [("p", "Founded in 2020.")] * 6
    right = [
        ("h", "Required Skills"),
        ("p", "- Python"),
        ("p", "- FastAPI"),
        ("p", "- PostgreSQL"),
        ("p", "- Celery"),
        ("p", "- Docker"),
        ("p", "- Azure"),
        ("h", "Nice to Have"),
        ("p", "- Go"),
    ]

    result = locate_jd_requirements(_build_pdf([[(50, left), (330, right)]]), "jd.pdf")

    assert result["heading"] == "Required Skills"
    assert _lines(result["section_text"]) == [
        "- python",
        "- fastapi",
        "- postgresql",
        "- celery",
        "- docker",
        "- azure",
    ]  # nothing from the unrelated left column


def test_pdf_two_columns_right_column_continues_the_list():
    left = REQS + [("p", "- REST API design"), ("p", "- Git")]
    right = [
        ("p", "- Redis caching"),
        ("p", "- Linux basics"),
        ("p", "- Unit testing"),
        ("p", "- Message queues"),
        ("p", "- Terraform"),
        ("p", "- Monitoring"),
        ("h", "Benefits"),
        ("p", "- Health cover"),
    ]

    text = locate_jd_requirements(_build_pdf([[(50, left), (330, right)]]), "jd.pdf")[
        "section_text"
    ]

    # Continuation columns are pulled in...
    for expected in ("linux basics", "unit testing", "terraform", "monitoring"):
        assert expected in text

    # ...but the Benefits block after them is not.
    assert "health cover" not in text

    # KNOWN QUIRK (inherited from the source notebook, deliberately not
    # asserted either way): when the right column starts on the same row
    # as the left column's heading, that first right-column line
    # ("- Redis caching" here) is treated as part of the heading row and
    # dropped; and a boundary heading in the right column can cut a
    # left-column line at the same height. If you change that logic in
    # jd_skills_locator._locate_in_pdf_bytes, tighten this test.


def test_pdf_requirements_continue_onto_next_page():
    page1 = [
        (50, [("h", "About the Role")] + [("p", f"filler {i}") for i in range(30)]
         + [("h", "Requirements"), ("p", "- Python"), ("p", "- SQL")])
    ]
    page2 = [(50, [("p", "- Docker"), ("p", "- AWS"), ("h", "Benefits"), ("p", "- x")])]

    result = locate_jd_requirements(_build_pdf([page1, page2]), "jd.pdf")

    assert _lines(result["section_text"]) == ["- python", "- sql", "- docker", "- aws"]


def test_pdf_boundary_glued_onto_last_requirement_is_split():
    raw = _build_pdf(
        [
            [
                (
                    50,
                    [
                        ("h", "Requirements"),
                        ("p", "- Python"),
                        ("p", "- SQL"),
                        ("p", "- own the deploy pipeline Company & Culture"),
                        ("p", "- We value kindness"),
                    ],
                )
            ]
        ]
    )

    result = locate_jd_requirements(raw, "jd.pdf")

    assert _lines(result["section_text"]) == [
        "- python",
        "- sql",
        "- own the deploy pipeline",
    ]


def test_pdf_without_requirements_section_is_not_found_not_an_error():
    raw = _build_pdf(
        [[(50, [("h", "About the Role"), ("p", "We build."), ("h", "Benefits")])]]
    )

    assert locate_jd_requirements(raw, "jd.pdf") == {
        "found": False,
        "section_text": "",
        "heading": None,
    }


def test_corrupt_pdf_raises_instead_of_silently_failing():
    with pytest.raises(Exception):
        locate_jd_requirements(b"this is not a pdf", "jd.pdf")


# ---------------------------------------------------------------------
# Flat-text path (DOCX / TXT / jd_raw_text fallback)
# ---------------------------------------------------------------------


def test_flat_text_basic():
    text = (
        "About the role\nWe build.\n\nRequirements\n- Python\n- SQL\n- AWS\n"
        "- Docker\n\nNice to have\n- Go\n"
    )

    result = locate_required_skills(text)

    assert result["heading"] == "Requirements"
    assert _lines(result["section_text"]) == ["- Python", "- SQL", "- AWS", "- Docker"]


def test_flat_text_all_caps_skill_lines_do_not_end_the_section():
    """Regression: a lone 'SQL' / 'AWS' line is all-caps but is a skill,
    not a heading, and must not truncate the section."""
    text = "Requirements\n- Python\nSQL\nAWS\n- SQL\n\nBenefits\n- Health\n"

    lines = _lines(locate_required_skills(text)["section_text"])

    assert lines == ["- Python", "SQL", "AWS", "- SQL"]


def test_flat_text_empty_input():
    assert locate_required_skills("")["found"] is False


@pytest.mark.parametrize(
    "line, expected",
    [
        ("Benefits", True),
        ("Nice to Have", True),
        ("ABOUT THE TEAM", True),
        ("SQL", False),
        ("- SQL", False),
        ("- 3+ years Python", False),
    ],
)
def test_is_section_boundary(line, expected):
    assert is_section_boundary(line) is expected


def test_embedded_boundary_needs_heading_capitalisation():
    assert split_embedded_section_boundary("own the pipeline Company & Culture") == (
        "own the pipeline",
        "Company & Culture",
    )
    # Prose that merely contains a boundary word must not be cut.
    assert split_embedded_section_boundary("work on our benefits platform") == (
        "work on our benefits platform",
        None,
    )


# ---------------------------------------------------------------------
# Dispatcher: file types the upload route accepts (PDF / DOCX) + TXT
# ---------------------------------------------------------------------


def test_dispatch_txt():
    raw = (
        b"About the Role\nWe build a hiring platform used by recruiters daily.\n\n"
        b"Required Skills\n- Python\n- SQL\n- AWS\n\nBenefits\n- Health\n"
    )

    result = locate_jd_requirements(raw, "jd.txt")

    assert result["heading"] == "Required Skills"
    assert _lines(result["section_text"]) == ["- Python", "- SQL", "- AWS"]


def test_dispatch_docx():
    docx = pytest.importorskip("docx")

    document = docx.Document()
    for line in [
        "Senior Backend Engineer",
        "We build a hiring platform used by many recruiters every day.",
        "Requirements",
        "3+ years of Python",
        "SQL and PostgreSQL",
        "Nice to Have",
        "Go",
    ]:
        document.add_paragraph(line)

    buffer = io.BytesIO()
    document.save(buffer)

    result = locate_jd_requirements(buffer.getvalue(), "jd.docx")

    assert result["heading"] == "Requirements"
    assert _lines(result["section_text"]) == ["3+ years of Python", "SQL and PostgreSQL"]


def test_dispatch_unsupported_type_raises():
    with pytest.raises(Exception):
        locate_jd_requirements(b"hello", "jd.xyz")


# ---------------------------------------------------------------------
# Celery task wiring: stored file -> locate -> clean -> LLM -> persist.
# The LLM, storage, and DB session are faked; the locator, text prep and
# postprocess_skills run for real.
# ---------------------------------------------------------------------


class _FakeDB:
    def __init__(self, job):
        self._job = job
        self.commits = 0

    def get(self, _model, _id):
        return self._job

    def commit(self):
        self.commits += 1

    def close(self):
        pass


def _fake_job(**overrides):
    fields = dict(
        blob_path="unowned/abc.pdf",
        original_filename="jd.pdf",
        jd_raw_text=None,
        skills_result=None,
        skills_section_heading=None,
        skills_extraction_status=None,
        skills_extraction_error=None,
        skills_extracted_at=None,
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest.fixture
def task_env(monkeypatch):
    from app.core import jd_skills_extraction_tasks as tasks

    seen = {}

    def install(job, blob_bytes=b"", llm=None):
        monkeypatch.setattr(tasks, "SessionLocal", lambda: _FakeDB(job))
        monkeypatch.setattr(tasks, "download_resume_blob", lambda path: blob_bytes)

        def fake_llm(prepared_text):
            seen["llm_input"] = prepared_text
            return llm(prepared_text) if llm else []

        monkeypatch.setattr(tasks, "extract_jd_skills_only", fake_llm)
        return tasks, seen

    return install


def test_task_pdf_reaches_llm_with_only_the_requirements_text(task_env):
    raw = _build_pdf(
        [[(50, [("h", "About the Role"), ("p", "We build.")] + REQS + [("h", "Benefits")])]]
    )
    job = _fake_job()
    tasks, seen = task_env(job, raw, llm=lambda text: ["python", "sql", "kubernetes"])

    tasks.run_jd_skills_extraction_task.run("job-1")

    assert "years python" in seen["llm_input"]
    assert "about the role" not in seen["llm_input"]
    assert "benefits" not in seen["llm_input"]
    assert job.skills_extraction_status.value == "done"
    assert job.skills_section_heading == "Requirements"
    assert job.skills_result == ["python", "sql", "kubernetes"]


def test_task_drops_skills_the_llm_invented(task_env):
    raw = _build_pdf([[(50, REQS + [("h", "Benefits")])]])
    job = _fake_job()
    tasks, _ = task_env(job, raw, llm=lambda text: ["python", "cobol"])

    tasks.run_jd_skills_extraction_task.run("job-1")

    assert job.skills_result == ["python"]


def test_task_marks_failed_when_no_section_found(task_env):
    raw = _build_pdf([[(50, [("h", "About the Role"), ("p", "We build.")])]])
    job = _fake_job()
    tasks, seen = task_env(job, raw)

    tasks.run_jd_skills_extraction_task.run("job-1")

    assert job.skills_extraction_status.value == "failed"
    assert "required-skills section" in job.skills_extraction_error
    assert "llm_input" not in seen  # the LLM is never called


def test_task_marks_failed_on_unsupported_file_type(task_env):
    job = _fake_job(original_filename="jd.xyz")
    tasks, _ = task_env(job, b"hello")

    tasks.run_jd_skills_extraction_task.run("job-1")

    assert job.skills_extraction_status.value == "failed"


def test_task_without_stored_file_falls_back_to_raw_text(task_env):
    job = _fake_job(
        blob_path=None,
        jd_raw_text="Requirements\n- Python\n- SQL\n\nBenefits\n- Health\n",
    )
    tasks, seen = task_env(job, llm=lambda text: ["python"])

    tasks.run_jd_skills_extraction_task.run("job-1")

    assert "python" in seen["llm_input"]
    assert job.skills_extraction_status.value == "done"


def test_task_with_nothing_to_read_fails_cleanly(task_env):
    job = _fake_job(blob_path=None, jd_raw_text=None)
    tasks, _ = task_env(job)

    tasks.run_jd_skills_extraction_task.run("job-1")

    assert job.skills_extraction_status.value == "failed"