"""
Tests for /metrics, task metrics (via Redis), and the Redis/worker health
endpoints. No real Redis, Celery worker or database: Redis is replaced by
a tiny in-memory fake. tests/conftest.py's DB bootstrap is overridden with
a no-op, same as tests/test_jd_locator.py.
"""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from app.api.routes import health, metrics as metrics_route
from app.core import metrics
from app.core.logging_config import RequestLoggingMiddleware


@pytest.fixture(scope="session", autouse=True)
def _prepare_test_database():
    yield


class FakeRedis:
    def __init__(self, queues=None, fail=False):
        self.hashes: dict[str, dict[str, float]] = {}
        self.values: dict[str, float] = {}
        self.queues = queues or {}
        self.fail = fail

    def _check(self):
        if self.fail:
            raise ConnectionError("redis down")

    def ping(self):
        self._check()
        return True

    def llen(self, name):
        self._check()
        return self.queues.get(name, 0)

    def hgetall(self, key):
        self._check()
        return {k.encode(): str(v).encode() for k, v in self.hashes.get(key, {}).items()}

    def get(self, key):
        self._check()
        v = self.values.get(key)
        return None if v is None else str(v).encode()

    def pipeline(self):
        outer = self
        ops = []

        class Pipe:
            def hincrby(self, key, field, n):
                ops.append(("h", key, field, n))

            hincrbyfloat = hincrby

            def set(self, key, value):
                ops.append(("s", key, None, value))

            def execute(self):
                outer._check()
                for kind, key, field, n in ops:
                    if kind == "h":
                        h = outer.hashes.setdefault(key, {})
                        h[field] = h.get(field, 0) + n
                    else:
                        outer.values[key] = n

        return Pipe()


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis(queues={"llm": 7, "celery": 0})
    monkeypatch.setattr(metrics, "_redis", lambda: fake)
    monkeypatch.setattr(
        metrics, "_count_stuck_rows", lambda: {"resume_extraction_pending": 2, "match_scoring_failed": 0}
    )
    metrics.register_collector()
    return fake


def _scrape() -> str:
    return generate_latest().decode()


def test_task_metrics_round_trip_through_redis(fake_redis):
    metrics.record_task("skills_extraction.run", "SUCCESS", 2.5)
    metrics.record_task("skills_extraction.run", "SUCCESS", 1.5)
    metrics.record_task("skills_extraction.run", "FAILURE", 0.5)

    text = _scrape()

    assert 'talentmatch_task_runs_total{state="SUCCESS",task="skills_extraction.run"} 2.0' in text
    assert 'talentmatch_task_runs_total{state="FAILURE",task="skills_extraction.run"} 1.0' in text
    assert 'talentmatch_task_duration_seconds_count{task="skills_extraction.run"} 3.0' in text
    assert 'talentmatch_task_duration_seconds_sum{task="skills_extraction.run"} 4.5' in text
    assert "talentmatch_last_task_finished_timestamp_seconds 1." in text  # a real unix time


def test_queue_depth_and_stuck_rows_are_exposed(fake_redis):
    text = _scrape()

    assert 'talentmatch_queue_depth{queue="llm"} 7.0' in text
    assert 'talentmatch_queue_depth{queue="celery"} 0.0' in text
    assert 'talentmatch_stuck_rows{kind="resume_extraction_pending"} 2.0' in text
    assert "talentmatch_redis_up 1.0" in text


def test_scrape_survives_redis_outage(monkeypatch):
    down = FakeRedis(fail=True)
    monkeypatch.setattr(metrics, "_redis", lambda: down)
    monkeypatch.setattr(metrics, "_count_stuck_rows", lambda: {})
    metrics.register_collector()

    assert "talentmatch_redis_up 0.0" in _scrape()


def test_record_task_never_raises_when_redis_is_down(monkeypatch):
    monkeypatch.setattr(metrics, "_redis", lambda: FakeRedis(fail=True))

    metrics.record_task("x.run", "SUCCESS", 1.0)  # must not raise


def test_http_metrics_use_route_template_not_raw_url(fake_redis):
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/items/{item_id}")
    def item(item_id: int):
        return {"id": item_id}

    client = TestClient(app)
    for i in (1, 2, 3):
        client.get(f"/items/{i}")
    client.get("/nope-1")
    client.get("/nope-2")

    text = _scrape()

    assert 'route="/items/{item_id}"' in text
    assert 'route="/items/1"' not in text
    assert 'route="unmatched"' in text and 'route="/nope-1"' not in text


def _metrics_client():
    app = FastAPI()
    app.include_router(metrics_route.router)
    return TestClient(app)


def test_metrics_open_in_development(fake_redis, monkeypatch):
    monkeypatch.setattr(metrics_route.settings, "ENV", "development")
    monkeypatch.setattr(metrics_route.settings, "METRICS_TOKEN", None)

    resp = _metrics_client().get("/metrics")

    assert resp.status_code == 200
    assert "talentmatch_queue_depth" in resp.text


def test_metrics_hidden_in_production_without_token(fake_redis, monkeypatch):
    monkeypatch.setattr(metrics_route.settings, "ENV", "production")
    monkeypatch.setattr(metrics_route.settings, "METRICS_TOKEN", None)

    assert _metrics_client().get("/metrics").status_code == 404


def test_metrics_token_is_enforced(fake_redis, monkeypatch):
    monkeypatch.setattr(metrics_route.settings, "METRICS_TOKEN", "s3cret-token")
    client = _metrics_client()

    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer s3cret-token"}).status_code == 200


# ---------------------------------------------------------------------
# /api/health/redis and /api/health/worker
# ---------------------------------------------------------------------


def _health_client():
    app = FastAPI()
    app.include_router(health.router, prefix="/api")
    return TestClient(app)


def test_health_redis_ok_and_down(monkeypatch):
    monkeypatch.setattr(metrics, "_redis", lambda: FakeRedis())
    assert _health_client().get("/api/health/redis").json() == {"status": "ok", "redis": "connected"}

    monkeypatch.setattr(metrics, "_redis", lambda: FakeRedis(fail=True))
    resp = _health_client().get("/api/health/redis")
    assert resp.status_code == 503 and resp.json()["status"] == "error"


def _patch_ping(monkeypatch, result):
    from app.core.celery_app import celery_app

    monkeypatch.setattr(
        celery_app.control, "inspect", lambda timeout=None: SimpleNamespace(ping=lambda: result)
    )


def test_health_worker_ok_reports_workers_and_queue_depth(monkeypatch):
    monkeypatch.setattr(metrics, "_redis", lambda: FakeRedis(queues={"llm": 4}))
    _patch_ping(monkeypatch, {"celery@w1": {"ok": "pong"}})

    resp = _health_client().get("/api/health/worker")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "workers": ["celery@w1"], "queues": {"celery": 0, "llm": 4}}


def test_health_worker_503_when_nobody_answers(monkeypatch):
    monkeypatch.setattr(metrics, "_redis", lambda: FakeRedis())
    _patch_ping(monkeypatch, None)

    resp = _health_client().get("/api/health/worker")

    assert resp.status_code == 503
    assert resp.json()["workers"] == []
