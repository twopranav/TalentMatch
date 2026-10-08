"""
Tests for the resume section locators (app/core/skills_pdf_locator.py:
Skills / Experience / Projects) and the three-source prep helpers in
app/core/skills_text_prep.py. Pure: no database, Redis or LLM, so the
DB fixtures from conftest.py are overridden with no-ops.
"""

import io

import pytest

from app.core.skills_pdf_locator import locate_resume_sections
from app.core.skills_text_prep import (
    build_skill_blocks,
    clean_prose,
    merge_source_skills,
    reroute_leaks,
)


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield


HEADINGS = {"SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION", "HOBBIES"}


def _pdf(pages: list[list[tuple[float, float, str]]]) -> bytes:
    """pages -> [(x, y, text)]; headings are drawn bold so they share a style."""
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for page in pages:
        for x, y, text in page:
            c.setFont("Helvetica-Bold" if text in HEADINGS else "Helvetica", 12)
            c.drawString(x, y, text)
        c.showPage()
    c.save()
    return buf.getvalue()


def _column(lines, x=50, top=780):
    return [(x, top - 18 * i, line) for i, line in enumerate(lines)]


SINGLE_COLUMN = [
    "Jane Doe",
    "EXPERIENCE",
    "Acme Corp - Backend Engineer",
    "Built REST APIs in Python.",
    "Deployed to AWS with Docker.",
    "PROJECTS",
    "Resume Matcher: FastAPI, Kafka",
    "Ranked applicants using embeddings.",
    "SKILLS",
    "Python, SQL",
    "Docker",
    "HOBBIES",
    "Chess and climbing",
    "EDUCATION",
    "BSc Computer Science",
]


def test_pdf_locates_all_three_sections_and_stops_at_the_next_heading():
    located = locate_resume_sections(_pdf([_column(SINGLE_COLUMN)]), "r.pdf")

    assert located["skills"]["found"] and located["skills"]["heading"] == "SKILLS"
    assert located["skills"]["section_text"].splitlines() == ["Python, SQL", "Docker"]

    assert located["experience"]["heading"] == "EXPERIENCE"
    assert located["experience"]["section_text"].splitlines() == [
        "Acme Corp - Backend Engineer",
        "Built REST APIs in Python.",
        "Deployed to AWS with Docker.",
    ]

    assert located["projects"]["section_text"].splitlines() == [
        "Resume Matcher: FastAPI, Kafka",
        "Ranked applicants using embeddings.",
    ]


def test_heading_missing_from_the_vocabulary_still_ends_the_section_above_it():
    # "HOBBIES" is not special-cased by name in the skills locator; the
    # skills block must not swallow "Chess and climbing" ... and the
    # experience block above must not either.
    located = locate_resume_sections(_pdf([_column(SINGLE_COLUMN)]), "r.pdf")

    assert "Chess" not in located["skills"]["section_text"]
    assert "Chess" not in located["experience"]["section_text"]
    assert "Chess" not in located["projects"]["section_text"]


def test_missing_sections_are_reported_not_found():
    lines = ["Jane Doe", "EXPERIENCE", "Acme Corp - Backend Engineer", "Built things."]
    located = locate_resume_sections(_pdf([_column(lines)]), "r.pdf")

    assert located["experience"]["found"]
    assert located["projects"] == {"found": False, "heading": None, "section_text": ""}
    assert not located["skills"]["found"]


def test_two_column_layout_reads_each_lane_separately():
    left = ["SKILLS"] + [f"skill{i}, tool{i}" for i in range(8)]
    right = ["EXPERIENCE"] + [f"Did thing number {i} at Acme" for i in range(8)]
    pdf = _pdf([_column(left, x=40) + _column(right, x=330)])

    located = locate_resume_sections(pdf, "r.pdf")

    assert "skill0, tool0" in located["skills"]["section_text"]
    assert "Did thing" not in located["skills"]["section_text"]
    assert "Did thing number 0 at Acme" in located["experience"]["section_text"]
    assert "skill0" not in located["experience"]["section_text"]


def test_experience_continues_across_pages_and_running_header_is_dropped():
    page1 = _column(["Jane Doe - Resume", "EXPERIENCE", "Acme Corp", "Built APIs."])
    page2 = _column(["Jane Doe - Resume", "Later promoted to lead.", "PROJECTS", "Matcher"])
    located = locate_resume_sections(_pdf([page1, page2]), "r.pdf")

    text = located["experience"]["section_text"]
    assert "Later promoted to lead." in text
    assert "Jane Doe - Resume" not in text
    assert located["projects"]["section_text"] == "Matcher"


def test_txt_path_uses_vocabulary_headings_only():
    body = (
        "Jane Doe\n"
        "Work Experience\n"
        "ACME CORP\n"                 # ALL-CAPS employer must NOT end the section
        "Built REST APIs in Python and deployed them.\n"
        "Projects\n"
        "Resume Matcher using FastAPI and embeddings.\n"
        "Skills\n"
        "Python, SQL, Docker\n"
        "Education\n"
        "BSc Computer Science\n"
    )
    located = locate_resume_sections(body.encode(), "r.txt")

    assert located["experience"]["heading"] == "Work Experience"
    assert "ACME CORP" in located["experience"]["section_text"]
    assert located["projects"]["section_text"] == "Resume Matcher using FastAPI and embeddings."
    assert located["skills"]["section_text"] == "Python, SQL, Docker"


# ---------------------------------------------------------------- prep helpers


def test_clean_prose_drops_bullets_and_blank_lines_only():
    assert clean_prose("• Built APIs\n\n- Led team\n(cid:127) Shipped") == "Built APIs\nLed team\nShipped"
    assert clean_prose(None) == ""


def test_build_skill_blocks_cleans_skills_and_leaves_prose_alone():
    located = {
        "skills": {"found": True, "heading": "Skills", "section_text": "Cloud & DevOps: AWS (ECS, S3)\nLanguages:\nPython"},
        "experience": {"found": True, "heading": "Experience", "section_text": "• Built APIs in Go"},
        "projects": {"found": False, "heading": None, "section_text": ""},
    }
    assert build_skill_blocks(located) == {
        "skills_section": "aws, aws ecs, aws s3\npython",
        "work_experience": "Built APIs in Go",
        "projects": "",
    }


def test_reroute_leaks_moves_a_skill_to_the_block_it_appears_in():
    blocks = {"skills_section": "python", "work_experience": "used kafka daily", "projects": ""}
    raw = {"skills_section": ["python", "kafka"], "work_experience": [], "projects": ["cobol"]}

    routed = reroute_leaks(raw, blocks)

    assert routed["skills_section"] == ["python"]
    assert routed["work_experience"] == ["kafka"]
    assert routed["projects"] == ["cobol"]  # in no block: stays put, dropped later as hallucinated


def test_merge_source_skills_dedupes_case_insensitively_in_source_order():
    merged = merge_source_skills(
        {
            "projects": ["FastAPI", "Redis"],
            "skills_section": ["python", "redis"],
            "work_experience": ["Python", "go"],
        }
    )
    assert merged == ["python", "redis", "go", "FastAPI"]
