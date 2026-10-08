"""Pure tests for fill_source_occurrences (app/core/skills_text_prep.py)."""

import pytest

from app.core.skills_text_prep import fill_source_occurrences


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield


BLOCKS = {
    "skills_section": "python, sql, c++, java",
    "work_experience": "built apis in python. wrote c++ tooling and sql reports.",
    "projects": "a javascript dashboard using fastapi",
}


def test_adds_a_skill_to_every_block_that_contains_it():
    by_source = {"skills_section": ["python", "sql", "c++", "java"],
                 "work_experience": [], "projects": ["fastapi"]}
    out = fill_source_occurrences(by_source, BLOCKS)
    assert out["work_experience"] == ["python", "sql", "c++"]
    assert out["projects"] == ["fastapi"]
    assert out["skills_section"] == ["python", "sql", "c++", "java"]


def test_whole_word_only_java_is_not_javascript():
    by_source = {"skills_section": ["java"], "work_experience": [], "projects": []}
    out = fill_source_occurrences(by_source, BLOCKS)
    assert out["projects"] == []          # "javascript" must not count as "java"


def test_c_does_not_match_inside_cpp():
    by_source = {"skills_section": ["c"], "work_experience": [], "projects": []}
    out = fill_source_occurrences(by_source, BLOCKS)
    assert out["work_experience"] == []   # only "c++" is there, never plain "c"


def test_never_invents_a_skill_and_keeps_existing_order():
    by_source = {"skills_section": [], "work_experience": ["sql", "python"], "projects": []}
    out = fill_source_occurrences(by_source, BLOCKS)
    assert out["skills_section"] == ["sql", "python"]
    assert out["work_experience"] == ["sql", "python"]
    assert out["projects"] == []


def test_empty_input_is_fine():
    empty = {"skills_section": [], "work_experience": [], "projects": []}
    assert fill_source_occurrences(empty, {k: "" for k in empty}) == empty
