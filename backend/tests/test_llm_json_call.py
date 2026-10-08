"""
Tests for the retry behaviour in app/core/llm_json_call.py.

A scripted fake model stands in for Groq: each item in the script is either
an exception to raise or a response to return, consumed one per invoke().
time.sleep is replaced so tests run instantly and can assert the waits.

NOTE: FakeAPIError mimics the OpenAI-style error shape (.status_code and
.response.headers). That is an assumption until you've confirmed what a real
429 looks like in your logs -- see the "trigger a real 429" step.
"""

import json
from types import SimpleNamespace

import pytest

from app.core import llm_json_call


class BoomError(Exception):
    """Stands in for SkillsExtractionError."""


class FakeAPIError(Exception):
    def __init__(self, status_code=None, retry_after=None):
        super().__init__(f"fake provider error {status_code}")
        self.status_code = status_code
        headers = {} if retry_after is None else {"retry-after": str(retry_after)}
        self.response = SimpleNamespace(status_code=status_code, headers=headers)


def ok(skills=("python", "sql")):
    return SimpleNamespace(
        content=json.dumps({"skills": list(skills)}),
        response_metadata={"token_usage": {"prompt_tokens": 120, "completion_tokens": 15}},
    )


def ok_sources(**lists):
    body = {"skills_section": [], "work_experience": [], "projects": [], **lists}
    return SimpleNamespace(
        content=json.dumps(body),
        response_metadata={"token_usage": {"prompt_tokens": 200, "completion_tokens": 30}},
    )


def junk():
    return SimpleNamespace(content="not json at all", response_metadata={})


class FakeLLM:
    def __init__(self, script):
        self.script = list(script)
        self.calls = 0

    def bind(self, **_):
        return self

    def invoke(self, _messages):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def run(monkeypatch):
    """run(script, **call_kwargs) -> (result_or_exception, llm, sleeps)"""

    def _run(script, **call_kwargs):
        llm = FakeLLM(script)
        sleeps: list[float] = []
        monkeypatch.setattr(llm_json_call, "get_chat_model_for_task", lambda task: llm)
        monkeypatch.setattr(llm_json_call.time, "sleep", sleeps.append)
        try:
            result = llm_json_call.call_skills_model(
                task="t", system_prompt="p", document_text="d",
                schema_name="skills", error_cls=BoomError, **call_kwargs,
            )
        except BoomError as exc:
            result = exc
        return result, llm, sleeps

    return _run


def test_success_first_try_reports_tokens_and_attempts(run):
    (skills, meta), llm, sleeps = run([ok()])
    assert skills == ["python", "sql"]
    assert meta["prompt_tokens"] == 120 and meta["completion_tokens"] == 15
    assert meta["attempts"] == 1 and llm.calls == 1 and sleeps == []


def test_429_waits_for_retry_after_then_succeeds(run):
    (skills, meta), llm, sleeps = run([FakeAPIError(429, retry_after=3), ok()])
    assert skills == ["python", "sql"]
    assert sleeps == [3.0] and llm.calls == 2 and meta["attempts"] == 2


def test_429_without_hint_uses_exponential_backoff(run):
    _, llm, sleeps = run([FakeAPIError(429), FakeAPIError(429), ok()])
    assert sleeps == [2.0, 4.0] and llm.calls == 3


def test_429_asking_for_a_long_wait_gives_up_without_sleeping(run):
    result, llm, sleeps = run([FakeAPIError(429, retry_after=60), ok()])
    assert isinstance(result, BoomError)
    assert sleeps == [] and llm.calls == 1


def test_transient_errors_stop_after_the_retry_budget(run):
    script = [FakeAPIError(429)] * (llm_json_call._MAX_TRANSIENT_RETRIES + 1)
    result, llm, sleeps = run(script)
    assert isinstance(result, BoomError)
    assert llm.calls == llm_json_call._MAX_TRANSIENT_RETRIES + 1
    assert len(sleeps) == llm_json_call._MAX_TRANSIENT_RETRIES


@pytest.mark.parametrize("status", [400, 401, 413])
def test_non_retryable_errors_fail_immediately(run, status):
    result, llm, sleeps = run([FakeAPIError(status), ok()])
    assert isinstance(result, BoomError)
    assert llm.calls == 1 and sleeps == []


def test_server_errors_and_missing_status_are_retried(run):
    (skills, _), llm, _ = run([FakeAPIError(503), FakeAPIError(None), ok()])
    assert skills == ["python", "sql"] and llm.calls == 3


def test_bad_output_is_re_asked_once_without_waiting(run):
    (skills, meta), llm, sleeps = run([junk(), ok()])
    assert skills == ["python", "sql"]
    assert sleeps == [] and meta["attempts"] == 2


def test_bad_output_twice_raises(run):
    result, llm, sleeps = run([junk(), junk(), ok()])
    assert isinstance(result, BoomError)
    assert llm.calls == 2 and sleeps == []


_KEYS = ("skills_section", "work_experience", "projects")


def test_source_keys_returns_one_list_per_source(run):
    (skills, meta), llm, _ = run([ok_sources(projects=["fastapi"])], source_keys=_KEYS)
    assert skills == {"skills_section": [], "work_experience": [], "projects": ["fastapi"]}
    assert meta["prompt_tokens"] == 200 and llm.calls == 1


def test_source_keys_missing_a_key_is_bad_output(run):
    partial = SimpleNamespace(content=json.dumps({"skills_section": []}), response_metadata={})
    (skills, _), llm, _ = run([partial, ok_sources()], source_keys=_KEYS)
    assert llm.calls == 2 and set(skills) == set(_KEYS)


def test_groq_json_validate_failed_400_is_re_asked_once(run):
    bad = FakeAPIError(400)
    bad.args = ("Error code: 400 - json_validate_failed",)
    (skills, _), llm, sleeps = run([bad, ok()])
    assert skills == ["python", "sql"] and llm.calls == 2 and sleeps == []


def test_groq_json_validate_failed_twice_raises(run):
    def bad():
        exc = FakeAPIError(400)
        exc.args = ("json_validate_failed",)
        return exc

    result, llm, _ = run([bad(), bad(), ok()])
    assert isinstance(result, BoomError) and llm.calls == 2
