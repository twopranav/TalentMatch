"""
Tests for the work-bounding changes:

  * dispatch.acquire_once          -- atomic "only the first caller wins" lock
  * matching_tasks._dispatch_ids   -- dedupe + batching + staggered start
  * POST .../rescore               -- ignores a repeat inside the lock window
  * per-user limiters on bulk-apply, rescore and both extract-skills routes
  * LLM-quota metrics (waits, fallbacks, window usage) exported on /metrics
"""
import uuid

import fakeredis
import pytest
from prometheus_client import generate_latest

from app.core import dispatch, llm_quota, matching_tasks, metrics
from app.core.config import settings
from app.models.user import UserRole
from test_match_scoring import _seed_three  # reuse the seeding helper


@pytest.fixture(autouse=True)
def _clear_once_locks():
    dispatch._once_until.clear()
    yield
    dispatch._once_until.clear()


# ------------------------------------------------------------ acquire_once

def test_acquire_once_only_first_caller_wins(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "memory")
    assert dispatch.acquire_once("k", 60) is True
    assert dispatch.acquire_once("k", 60) is False
    assert dispatch.acquire_once("other", 60) is True  # keys are independent


def test_acquire_once_expires(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "memory")
    clock = {"t": 1000.0}
    monkeypatch.setattr(dispatch.time, "monotonic", lambda: clock["t"])
    assert dispatch.acquire_once("k", 60) is True
    clock["t"] += 61
    assert dispatch.acquire_once("k", 60) is True


def test_acquire_once_is_a_no_op_when_limiter_is_off():
    assert settings.RATE_LIMIT_BACKEND == "off"  # conftest default
    assert dispatch.acquire_once("k", 60) is True
    assert dispatch.acquire_once("k", 60) is True


def test_acquire_once_uses_redis_set_nx(monkeypatch):
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(dispatch.rate_limit, "get_redis", lambda: fake)
    assert dispatch.acquire_once("job-1", 60) is True
    assert dispatch.acquire_once("job-1", 60) is False
    assert 0 < fake.ttl("once:job-1") <= 60


def test_acquire_once_falls_back_to_memory_when_redis_errors(monkeypatch):
    class Broken:
        def set(self, *a, **k):
            raise ConnectionError("down")

    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "redis")
    monkeypatch.setattr(dispatch.rate_limit, "get_redis", lambda: Broken())
    monkeypatch.setattr(dispatch.rate_limit, "mark_redis_down", lambda: None)
    assert dispatch.acquire_once("k", 60) is True
    assert dispatch.acquire_once("k", 60) is False


# ------------------------------------------------------------ _dispatch_ids

def test_dispatch_ids_dedupes_batches_and_staggers(monkeypatch):
    monkeypatch.setattr(settings, "RESCORE_BATCH_SIZE", 2)
    monkeypatch.setattr(settings, "RESCORE_BATCH_DELAY_SECONDS", 5)
    immediate, delayed = [], []
    task = matching_tasks.score_application_task
    monkeypatch.setattr(task, "delay", lambda i: immediate.append(i))
    monkeypatch.setattr(
        task, "apply_async", lambda args, countdown: delayed.append((args[0], countdown))
    )

    n = matching_tasks._dispatch_ids(["a", "b", "a", "c", "d", "e", "b"])

    assert n == 5  # a,b,c,d,e -- duplicates dropped
    assert immediate == ["a", "b"]  # first batch starts right away
    assert delayed == [("c", 5), ("d", 5), ("e", 10)]  # later batches are staggered


def test_dispatch_ids_small_job_is_one_immediate_batch(monkeypatch, dispatched):
    n = matching_tasks._dispatch_ids([uuid.uuid4() for _ in range(4)])
    assert n == 4
    assert len(dispatched["score"]) == 4


# ------------------------------------------------------------ rescore route

def test_rescore_repeat_inside_lock_window_queues_nothing(
    client, db, make_user, auth_headers, dispatched, monkeypatch
):
    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "memory")
    recruiter, job, _ = _seed_three(db, make_user)
    url = f"/api/applications/job/{job.id}/rescore"

    first = client.post(url, headers=auth_headers(recruiter))
    second = client.post(url, headers=auth_headers(recruiter))

    assert first.status_code == 202 and first.json() == {"queued": 4}
    assert second.status_code == 202
    assert second.json() == {"queued": 0, "already_in_progress": True}
    assert len(dispatched["score"]) == 4  # not 8


# ------------------------------------------------------------ route limiters

def _recruiter(make_user, auth_headers):
    recruiter, _ = make_user(role=UserRole.RECRUITER)
    return auth_headers(recruiter)


@pytest.mark.parametrize(
    "path_fmt,body,limit",
    [
        ("/api/applications/job/{id}/rescore", None, 5),
        ("/api/applications/job/{id}/bulk", {"resume_ids": [str(uuid.uuid4())]}, 10),
        ("/api/resumes/{id}/extract-skills", None, 10),
        ("/api/jobs/{id}/extract-skills", None, 10),
    ],
)
def test_expensive_routes_are_rate_limited_per_user(
    client, make_user, auth_headers, monkeypatch, path_fmt, body, limit
):
    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "memory")
    headers = _recruiter(make_user, auth_headers)
    url = path_fmt.format(id=uuid.uuid4())  # unknown id -> 404, which is fine

    codes = [client.post(url, headers=headers, json=body).status_code for _ in range(limit + 1)]

    assert 429 not in codes[:limit]
    assert codes[limit] == 429


# ------------------------------------------------------------ quota events

def test_quota_events_emitted_by_llm_quota(monkeypatch):
    events = []
    monkeypatch.setattr(llm_quota, "record_quota_event", events.append)

    with pytest.raises(llm_quota.TokenBudgetError):
        llm_quota.try_reserve(10_000, rpm_limit=30, tpm_limit=1000)
    assert events == ["token_budget_rejected"]

    events.clear()
    answers = iter([(None, 0.0), (llm_quota.Reservation("x", 5, "memory"), 0.0)])
    monkeypatch.setattr(llm_quota, "try_reserve", lambda *a, **k: next(answers))
    monkeypatch.setattr(llm_quota.time, "sleep", lambda s: None)
    llm_quota.reserve(5, 30, 8000)
    assert events == ["wait"]


@pytest.fixture
def quota_redis(monkeypatch):
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr(metrics, "_redis", lambda: fake)
    monkeypatch.setattr(metrics, "_count_stuck_rows", lambda: {})
    monkeypatch.setattr(settings, "RATE_LIMIT_BACKEND", "redis")
    metrics.register_collector()
    return fake


def test_record_quota_event_is_silent_unless_redis_backend(monkeypatch):
    fake = fakeredis.FakeRedis()
    monkeypatch.setattr(metrics, "_redis", lambda: fake)
    metrics.record_quota_event("wait")  # backend is "off" here
    assert fake.hgetall(metrics._QUOTA_EVENTS_KEY) == {}


def test_quota_events_and_window_usage_are_exported(quota_redis):
    import time

    metrics.record_quota_event("wait")
    metrics.record_quota_event("wait")
    metrics.record_quota_event("redis_fallback")
    now_ms = int(time.time() * 1000)
    quota_redis.zadd(llm_quota.KEY, {"aaa:100": now_ms, "bbb:200": now_ms})
    quota_redis.zadd(llm_quota.KEY, {"old:999": now_ms - 120_000})  # outside the window

    text = generate_latest().decode()

    assert 'talentmatch_llm_quota_events_total{event="wait"} 2.0' in text
    assert 'talentmatch_llm_quota_events_total{event="redis_fallback"} 1.0' in text
    assert "talentmatch_llm_quota_tokens_in_window 300.0" in text
    assert "talentmatch_llm_quota_requests_in_window 2.0" in text


def test_quota_read_failure_does_not_flip_redis_up(monkeypatch):
    class NoZset(fakeredis.FakeRedis):
        def zrangebyscore(self, *a, **k):
            raise RuntimeError("boom")

    fake = NoZset()
    monkeypatch.setattr(metrics, "_redis", lambda: fake)
    monkeypatch.setattr(metrics, "_count_stuck_rows", lambda: {})
    metrics.register_collector()

    assert "talentmatch_redis_up 1.0" in generate_latest().decode()
