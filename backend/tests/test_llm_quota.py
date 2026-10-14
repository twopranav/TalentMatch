"""
Tests for app/core/llm_quota.py and its use by llm_json_call and the probe route.

No real Redis and no real provider: a fake clock drives the rolling window, and
the Redis path runs the real Lua scripts against fakeredis (skipped if
fakeredis/lupa aren't installed). Several fakeredis clients on one FakeServer
stand in for separate worker processes sharing one Redis.

With LLM_RPM_LIMIT=30 / LLM_TPM_LIMIT=8000 the effective budget is 27 requests
and 7200 tokens per 60s window (90% safety factor).
"""

import json
import threading
from types import SimpleNamespace

import pytest

from app.api.routes import llm_config as llm_routes
from app.core import llm_json_call, llm_quota
from app.core.config import settings

RPM, TPM = 30, 8000  # -> 27 req / 7200 tokens per window


class _Clock:
    def __init__(self):
        self.now = 1_000_000.0
        self.sleeps: list[float] = []

    def advance(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(llm_quota, "_now", lambda: c.now)
    monkeypatch.setattr(llm_quota.time, "sleep", c.advance)
    monkeypatch.setattr(llm_quota, "_redis", lambda: None)  # memory backend
    llm_quota.reset_memory_window()
    yield c
    llm_quota.reset_memory_window()


def _used_tokens() -> int:
    return sum(tokens for _, _, tokens in llm_quota._mem_window)


# ---------------------------------------------------------------------------
# Budget rules (memory backend)
# ---------------------------------------------------------------------------


def test_fits_boundary():
    assert llm_quota.fits(7200, TPM)
    assert not llm_quota.fits(7201, TPM)


def test_oversized_request_is_rejected_even_when_the_window_is_empty(clock):
    # The old limiter returned immediately on an empty window, whatever the size.
    assert _used_tokens() == 0
    with pytest.raises(llm_quota.TokenBudgetError):
        llm_quota.try_reserve(500_000, RPM, TPM)
    assert _used_tokens() == 0  # nothing was reserved


def test_full_window_blocks_then_admits_after_expiry(clock):
    llm_quota.reserve(4000, RPM, TPM)
    reservation, wait = llm_quota.try_reserve(4000, RPM, TPM)
    assert reservation is None
    assert 59 <= wait <= 61

    admitted = llm_quota.reserve(4000, RPM, TPM)  # blocking: sleeps via fake clock
    assert admitted.tokens == 4000
    assert sum(clock.sleeps) >= 60


def test_settle_releases_tokens_the_call_did_not_use(clock):
    r = llm_quota.reserve(6000, RPM, TPM)
    assert llm_quota.try_reserve(2000, RPM, TPM)[0] is None
    llm_quota.settle(r, 500)
    assert llm_quota.try_reserve(2000, RPM, TPM)[0] is not None


def test_settle_charges_an_overrun(clock):
    r = llm_quota.reserve(1000, RPM, TPM)
    llm_quota.settle(r, 7000)
    assert llm_quota.try_reserve(500, RPM, TPM)[0] is None


def test_request_cap_applies_independently_of_tokens(clock):
    for _ in range(27):
        assert llm_quota.try_reserve(10, RPM, TPM)[0] is not None
    assert llm_quota.try_reserve(10, RPM, TPM)[0] is None


def test_concurrent_callers_never_exceed_the_budget(clock):
    n_threads = 40
    barrier = threading.Barrier(n_threads)
    admitted: list[bool] = []

    def worker():
        barrier.wait()
        admitted.append(llm_quota.try_reserve(1000, RPM, TPM)[0] is not None)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sum(admitted) == 7  # 7 x 1000 <= 7200 < 8 x 1000
    assert _used_tokens() == 7000


# ---------------------------------------------------------------------------
# Redis backend (real Lua scripts on fakeredis)
# ---------------------------------------------------------------------------

# The skip is inside the fixture, so only the tests that need fakeredis are
# skipped when it (or lupa, which runs the Lua) isn't installed:
#     pip install fakeredis lupa


@pytest.fixture
def server():
    fakeredis = pytest.importorskip("fakeredis")
    pytest.importorskip("lupa")
    return fakeredis.FakeServer()


def _client(server):
    import fakeredis

    return fakeredis.FakeStrictRedis(server=server)


def test_two_processes_share_one_budget(clock, server, monkeypatch):
    process_a, process_b = _client(server), _client(server)

    monkeypatch.setattr(llm_quota, "_redis", lambda: process_a)
    r = llm_quota.reserve(5000, RPM, TPM)
    assert r.backend == "redis"

    monkeypatch.setattr(llm_quota, "_redis", lambda: process_b)
    reservation, wait = llm_quota.try_reserve(5000, RPM, TPM)
    assert reservation is None  # B sees A's usage
    assert 59 <= wait <= 61


def test_redis_reservation_is_atomic_under_concurrency(clock, server, monkeypatch):
    local = threading.local()
    monkeypatch.setattr(llm_quota, "_redis", lambda: local.client)

    n_threads = 40
    barrier = threading.Barrier(n_threads)
    admitted: list[bool] = []

    def worker():
        local.client = _client(server)  # each "process" has its own connection
        barrier.wait()
        admitted.append(llm_quota.try_reserve(1000, RPM, TPM)[0] is not None)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sum(admitted) == 7


def test_redis_settle_adjusts_the_reserved_amount(clock, server, monkeypatch):
    monkeypatch.setattr(llm_quota, "_redis", lambda: _client(server))

    r = llm_quota.reserve(6000, RPM, TPM)
    assert llm_quota.try_reserve(2000, RPM, TPM)[0] is None
    llm_quota.settle(r, 500)
    assert llm_quota.try_reserve(2000, RPM, TPM)[0] is not None

    r2 = llm_quota.reserve(100, RPM, TPM)
    llm_quota.settle(r2, 7000)
    assert llm_quota.try_reserve(500, RPM, TPM)[0] is None


def test_redis_window_expires(clock, server, monkeypatch):
    monkeypatch.setattr(llm_quota, "_redis", lambda: _client(server))
    llm_quota.reserve(7000, RPM, TPM)
    assert llm_quota.try_reserve(500, RPM, TPM)[0] is None
    clock.advance(61)
    assert llm_quota.try_reserve(500, RPM, TPM)[0] is not None


def test_redis_request_cap(clock, server, monkeypatch):
    monkeypatch.setattr(llm_quota, "_redis", lambda: _client(server))
    for _ in range(27):
        assert llm_quota.try_reserve(10, RPM, TPM)[0] is not None
    assert llm_quota.try_reserve(10, RPM, TPM)[0] is None


def test_redis_failure_falls_back_to_the_process_local_window(clock, monkeypatch):
    class DownRedis:
        def eval(self, *a, **k):
            raise ConnectionError("redis is down")

    marked = []
    monkeypatch.setattr(llm_quota, "_redis", lambda: DownRedis())
    monkeypatch.setattr(llm_quota.rate_limit, "mark_redis_down", lambda: marked.append(1))

    r = llm_quota.reserve(1000, RPM, TPM)
    assert r.backend == "memory"
    assert marked == [1]
    assert _used_tokens() == 1000


# ---------------------------------------------------------------------------
# llm_json_call integration
# ---------------------------------------------------------------------------


class _Boom(Exception):
    pass


def _response(total_tokens=None):
    usage = {"prompt_tokens": 100, "completion_tokens": 20}
    if total_tokens is not None:
        usage["total_tokens"] = total_tokens
    return SimpleNamespace(
        content=json.dumps({"skills": ["python"]}),
        response_metadata={"token_usage": usage},
    )


class _FakeLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def bind(self, **_):
        return self

    def invoke(self, _messages):
        self.calls += 1
        return self.responses.pop(0)


def _call(monkeypatch, llm, document_text="resume text", **kw):
    monkeypatch.setattr(llm_json_call, "get_chat_model_for_task", lambda task, **o: llm)
    return llm_json_call.call_skills_model(
        task="t", system_prompt="p", document_text=document_text,
        schema_name="skills", error_cls=_Boom, **kw,
    )


def test_oversized_input_fails_before_any_provider_call(clock, monkeypatch):
    llm = _FakeLLM(_response())
    with pytest.raises(_Boom, match="too large"):
        _call(monkeypatch, llm, document_text="x" * 40_000, rate_limits=(RPM, TPM))
    assert llm.calls == 0
    assert clock.sleeps == []  # failed fast, did not wait
    assert _used_tokens() == 0


def test_successful_call_settles_the_real_token_usage(clock, monkeypatch):
    llm = _FakeLLM(_response(total_tokens=300))
    _call(monkeypatch, llm, rate_limits=(RPM, TPM))
    assert _used_tokens() == 300  # not the ~1500 estimate


def test_usage_missing_keeps_the_estimate(clock, monkeypatch):
    llm = _FakeLLM(_response(total_tokens=None))
    _call(monkeypatch, llm, rate_limits=(RPM, TPM))
    assert _used_tokens() >= llm_json_call._EST_OUTPUT_TOKENS


def test_without_rate_limits_the_quota_is_untouched(clock, monkeypatch):
    llm = _FakeLLM(_response(total_tokens=300))
    _call(monkeypatch, llm)
    assert _used_tokens() == 0


# ---------------------------------------------------------------------------
# Probe endpoint uses the same quota
# ---------------------------------------------------------------------------


class _ProbeModel:
    def __init__(self):
        self.prompts = []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return SimpleNamespace(content="ok", response_metadata={"token_usage": {"total_tokens": 42}})


@pytest.fixture
def probe_model(monkeypatch):
    model = _ProbeModel()
    monkeypatch.setattr(llm_routes, "get_chat_model_for_task", lambda task, **o: model)
    monkeypatch.setattr(settings, "LLM_RPM_LIMIT", RPM)
    monkeypatch.setattr(settings, "LLM_TPM_LIMIT", TPM)
    return model


def test_probe_is_refused_when_the_shared_quota_is_full(clock, probe_model):
    llm_quota.reserve(7150, RPM, TPM)  # an extraction already holds the budget
    result = llm_routes.probe_llm_config("resume_skills", None)
    assert result["ok"] is False and result["stage"] == "rate_limited"
    assert probe_model.prompts == []  # never reached the provider


def test_probe_counts_against_the_quota(clock, probe_model):
    result = llm_routes.probe_llm_config("resume_skills", None)
    assert result["ok"] is True
    assert _used_tokens() == 42
