"""
Import-level wiring checks. No database, Redis or LLM.

These exist because a module that is imported at boot but missing from
the tree (a route importing a deleted task module, a Celery `include`
pointing at one, a file overwritten by a copy of its own test) takes the
whole API or worker down, and none of the behavioural tests can notice
that: they fail at import, before any assertion runs.
"""

import importlib

import pytest


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    """Override conftest's DB bootstrap: these tests are pure."""
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    """Override conftest's per-test TRUNCATE: these tests never touch the DB."""
    yield


def test_every_celery_include_is_importable():
    from app.core.celery_app import celery_app

    for module_name in celery_app.conf.include:
        importlib.import_module(module_name)


def test_extraction_tasks_are_registered_under_their_names():
    from app.core.celery_app import celery_app

    celery_app.loader.import_default_modules()

    assert "skills_extraction.run" in celery_app.tasks
    assert "jd_skills_extraction.run" in celery_app.tasks
    assert "extraction_retry_sweep.sweep_resumes" in celery_app.tasks
    assert "extraction_retry_sweep.sweep_jobs" in celery_app.tasks
    assert "match.score_application" in celery_app.tasks
    assert "match.sweep" in celery_app.tasks


def test_beat_schedule_points_at_registered_tasks():
    from app.core.celery_app import celery_app

    celery_app.loader.import_default_modules()

    for entry in celery_app.conf.beat_schedule.values():
        assert entry["task"] in celery_app.tasks


def test_upload_routes_dispatch_the_skills_tasks_not_a_leftover_one():
    """resumes.py must queue the task the apply gate actually waits on
    (skills_extraction_status), and jobs.py the JD one."""
    from app.api.routes import jobs, resumes
    from app.core.jd_skills_extraction_tasks import run_jd_skills_extraction_task
    from app.core.skills_extraction_tasks import run_skills_extraction_task

    assert resumes.run_skills_extraction_task is run_skills_extraction_task
    assert jobs.run_jd_skills_extraction_task is run_jd_skills_extraction_task


def test_app_boots():
    importlib.import_module("app.main")