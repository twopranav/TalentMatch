"""
Tests for structured logging and request-id propagation.

Pure: no database, Redis or network. tests/conftest.py has a session
autouse fixture that builds a Postgres test DB; it is overridden below
with a no-op, same as tests/test_jd_locator.py.
"""
import io
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging_config import (
    JsonFormatter,
    RequestIdFilter,
    RequestLoggingMiddleware,
    request_id_var,
)


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    yield


def _json_logger(name: str):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(name)
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    return logger, stream


def test_json_formatter_includes_request_id_and_extras():
    logger, stream = _json_logger("test.json")
    token = request_id_var.set("abc12345")
    try:
        logger.info("hello", extra={"resume_id": "r-1"})
    finally:
        request_id_var.reset(token)

    line = json.loads(stream.getvalue())
    assert line["message"] == "hello"
    assert line["level"] == "INFO"
    assert line["request_id"] == "abc12345"
    assert line["resume_id"] == "r-1"


def test_json_formatter_includes_exception():
    logger, stream = _json_logger("test.json.exc")
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed")

    line = json.loads(stream.getvalue())
    assert "ValueError: boom" in line["exception"]


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ok")
    def ok():
        return {"request_id": request_id_var.get()}

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    return app


def test_middleware_generates_request_id_and_exposes_it():
    client = TestClient(_app())
    resp = client.get("/ok")

    header = resp.headers["X-Request-ID"]
    assert len(header) >= 8
    assert resp.json()["request_id"] == header  # visible inside the handler


def test_middleware_keeps_valid_incoming_request_id():
    client = TestClient(_app())
    resp = client.get("/ok", headers={"X-Request-ID": "trace-1234abcd"})

    assert resp.headers["X-Request-ID"] == "trace-1234abcd"


@pytest.mark.parametrize("bad", ["short", "has space in it!!", "x" * 200, "a;b\tc12345"])
def test_middleware_replaces_unsafe_incoming_request_id(bad):
    client = TestClient(_app())
    resp = client.get("/ok", headers={"X-Request-ID": bad})

    assert resp.headers["X-Request-ID"] != bad


def test_middleware_logs_one_line_per_request_without_query_string(caplog):
    client = TestClient(_app())
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/ok?email=someone@example.com")

    records = [r for r in caplog.records if r.name == "app.request"]
    assert len(records) == 1
    rec = records[0]
    assert (rec.method, rec.path, rec.status) == ("GET", "/ok", 200)
    assert rec.duration_ms >= 0
    assert "someone@example.com" not in json.dumps(rec.__dict__, default=str)


def test_health_probe_is_not_logged_at_info(caplog):
    client = TestClient(_app())
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/api/health")

    assert [r for r in caplog.records if r.name == "app.request"] == []


def test_unhandled_error_is_logged_once_with_traceback(caplog):
    client = TestClient(_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger="app.request"):
        resp = client.get("/boom")

    assert resp.status_code == 500
    records = [r for r in caplog.records if r.name == "app.request"]
    assert len(records) == 1
    assert records[0].exc_info is not None
    assert records[0].status == 500


def test_request_id_is_reset_after_request():
    client = TestClient(_app())
    client.get("/ok")

    assert request_id_var.get() is None


# ---------------------------------------------------------------------
# Celery: request_id travels API -> worker
# ---------------------------------------------------------------------


def test_request_id_is_copied_into_task_message_headers():
    from app.core.celery_app import _attach_request_id

    headers: dict = {}
    token = request_id_var.set("req-from-api-1")
    try:
        _attach_request_id(headers=headers)
    finally:
        request_id_var.reset(token)

    assert headers["request_id"] == "req-from-api-1"


def test_no_header_added_outside_a_request():
    from app.core.celery_app import _attach_request_id

    headers: dict = {}
    _attach_request_id(headers=headers)

    assert "request_id" not in headers


def test_worker_adopts_request_id_from_message_and_clears_it_after(caplog):
    from app.core.celery_app import _task_finished_log, _task_started_log

    task = SimpleNamespace(name="skills_extraction.run", request=SimpleNamespace(request_id="req-from-api-1"))

    with caplog.at_level(logging.INFO, logger="app.task"):
        _task_started_log(task_id="t-1", task=task)
        assert request_id_var.get() == "req-from-api-1"
        _task_finished_log(task_id="t-1", task=task, state="SUCCESS")

    assert request_id_var.get() is None
    finished = [r for r in caplog.records if r.getMessage() == "task finished"][0]
    assert finished.state == "SUCCESS" and finished.duration_ms >= 0


def test_worker_falls_back_to_task_id_when_no_request_id():
    from app.core.celery_app import _task_finished_log, _task_started_log

    task = SimpleNamespace(name="match.sweep", request=SimpleNamespace())

    _task_started_log(task_id="beat-task-9", task=task)
    assert request_id_var.get() == "beat-task-9"
    _task_finished_log(task_id="beat-task-9", task=task, state="SUCCESS")
