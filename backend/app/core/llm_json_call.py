"""
Shared retry/parse/validate machinery behind the two standalone
skills-extraction calls (skills_llm_extract.py, jd_skills_llm_extract.py).
A call returns either one flat list of skills (JD) or, when
source_keys is given, one list per key (resume: skills section / work
experience / projects).
Kept separate from those two files so each keeps its own exception type,
prompt, and llm_configs task -- a resume-skills failure or model change
can never get confused with a JD-skills one.

Two different kinds of failure are retried, on separate budgets:

  * Transient (rate limit 429, timeout, 5xx): the call never produced an
    answer. Wait, then retry -- honouring the provider's retry-after hint.
    If the provider asks for a wait longer than _MAX_WAIT_SECONDS we give up
    immediately instead of parking a worker; the caller marks the resume
    FAILED and the retry sweep / a manual re-run picks it up later.
  * Bad output (empty, not JSON, wrong shape, or Groq's 400
    "json_validate_failed"): the model answered, badly. Re-ask once, no
    waiting.

Anything else (400, 401, 413 "request too large", ...) can never succeed
by repeating it, so it fails on the first attempt.
"""

import json
import logging
import time

from app.core.llm_client import get_chat_model_for_task

logger = logging.getLogger(__name__)

# Bad output: the model answered but not usably. One re-ask.
_RETRIES = 1

# Transient errors: waits are 2s, 4s, 8s unless the provider says otherwise.
_MAX_TRANSIENT_RETRIES = 3
_BASE_BACKOFF_SECONDS = 2.0
# A worker sleeping in here can't do other work, so never wait longer.
_MAX_WAIT_SECONDS = 20.0

# Groq (and OpenAI strict mode) require the top-level schema to be an
# object, so the array of skills lives under a "skills" key.
_SKILLS_JSON_SCHEMA = {
    "type": "object",
    "properties": {"skills": {"type": "array", "items": {"type": "string"}}},
    "required": ["skills"],
    "additionalProperties": False,
}

# Appended to the system prompt because the prompt files describe a bare
# JSON array, which would contradict the object schema above.
_OUTPUT_FORMAT_NOTE = (
    '\n\nOutput format: return a JSON object of the form {"skills": ["...", "..."]}. '
    "Put the array you would otherwise return under the \"skills\" key. "
    "Return nothing else."
)


def _schema_for_sources(source_keys: tuple[str, ...]) -> dict:
    """One string array per source, all required. The prompt itself
    describes this shape, so no output-format note is appended."""
    return {
        "type": "object",
        "properties": {k: {"type": "array", "items": {"type": "string"}} for k in source_keys},
        "required": list(source_keys),
        "additionalProperties": False,
    }


def _is_string_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(i, str) for i in value)


def content_to_text(content) -> str:
    """Normalize an LLM message's `content` to plain text.

    Providers return either a string or a list of content parts
    (strings, dicts with a "text" key, or objects with a .text attribute).
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                text = getattr(part, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(content)


# ---------------------------------------------------------------------
# Error classification. Written defensively with getattr because the exact
# exception type that comes out of LangChain/ChatOpenAI hasn't been
# confirmed in your logs yet (see the TODO this replaces). OpenAI-style
# errors normally carry .status_code and .response.headers; if yours
# don't, everything falls into "transient", which is the safe default.
# ---------------------------------------------------------------------


def _status_code(exc: Exception) -> int | None:
    code = getattr(exc, "status_code", None)
    if code is None:
        code = getattr(getattr(exc, "response", None), "status_code", None)
    return code if isinstance(code, int) else None


def _retry_after_seconds(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if not headers:
        return None
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


def _is_transient(exc: Exception) -> bool:
    code = _status_code(exc)
    if code is None:
        return True  # timeouts / connection errors carry no status code
    return code in (408, 429) or code >= 500


def _wait_seconds(exc: Exception, retry_number: int) -> float | None:
    """Seconds to sleep before retry number `retry_number` (1-based), or
    None if the provider wants us to wait longer than we're willing to."""
    hinted = _retry_after_seconds(exc)
    if hinted is None:
        return min(_BASE_BACKOFF_SECONDS * 2 ** (retry_number - 1), _MAX_WAIT_SECONDS)
    if hinted > _MAX_WAIT_SECONDS:
        return None
    return hinted


_EST_OUTPUT_TOKENS = 1500  # throttle's guess for one call's output size (reasoning models use well over 1k)
_WINDOW: list[tuple[float, int]] = []  # (timestamp, tokens) of calls in the last 60s


def _throttle(est_tokens: int, rpm_limit: int, tpm_limit: int) -> None:
    while True:
        now = time.monotonic()
        _WINDOW[:] = [(t, k) for t, k in _WINDOW if now - t < 60]
        used = sum(k for _, k in _WINDOW)
        if not _WINDOW or (
            len(_WINDOW) < rpm_limit * 0.9 and used + est_tokens <= tpm_limit * 0.9
        ):
            return
        wait = 60 - (now - _WINDOW[0][0]) + 0.5
        logger.info(
            "throttle: %d req / %d tok in last 60s -> waiting %.0fs",
            len(_WINDOW), used, wait,
        )
        time.sleep(max(wait, 1))


def call_skills_model(
    *,
    task: str,
    system_prompt: str,
    document_text: str,
    schema_name: str,
    error_cls: type[Exception],
    source_keys: tuple[str, ...] | None = None,
    model_overrides: dict | None = None,
    rate_limits: tuple[int, int] | None = None,  # (rpm, tpm)
) -> tuple[list[str] | dict[str, list[str]], dict]:
    """Returns (skills, meta). skills is a flat list, or -- when
    source_keys is given -- a dict with exactly those keys."""
    schema = _schema_for_sources(source_keys) if source_keys else _SKILLS_JSON_SCHEMA
    system_content = system_prompt if source_keys else system_prompt + _OUTPUT_FORMAT_NOTE

    llm = get_chat_model_for_task(task, **(model_overrides or {})).bind(
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": schema, "strict": True},
        }
    )

    est = (len(system_content) + len(document_text)) // 4 + _EST_OUTPUT_TOKENS
    last_error: Exception | None = None
    start = time.monotonic()
    attempts = 0
    transient_retries = 0
    bad_output_retries = 0

    while True:
        attempts += 1
        if rate_limits:
            _throttle(est, *rate_limits)

        try:
            response = llm.invoke(
                [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": document_text},
                ]
            )
        except Exception as exc:
            if rate_limits:
                _WINDOW.append((time.monotonic(), est))
            last_error = exc
            code = _status_code(exc)

            # Groq rejects malformed model JSON with a 400. That is the
            # model answering badly, not a bad request: re-ask once.
            if code == 400 and "json_validate_failed" in str(exc):
                bad_output_retries += 1
                logger.warning(
                    "%s call returned unusable output on attempt %d: %s",
                    schema_name, attempts, exc,
                )
                if bad_output_retries > _RETRIES:
                    break
                continue

            if not _is_transient(exc):
                logger.warning(
                    "%s call failed with non-retryable error (status %s): %s",
                    schema_name, code, exc,
                )
                break

            transient_retries += 1
            if transient_retries > _MAX_TRANSIENT_RETRIES:
                logger.warning(
                    "%s call still failing after %d transient retries (status %s): %s",
                    schema_name, _MAX_TRANSIENT_RETRIES, code, exc,
                )
                break

            delay = _wait_seconds(exc, transient_retries)
            if delay is None:
                logger.warning(
                    "%s call asked to wait longer than %.0fs (status %s); giving up: %s",
                    schema_name, _MAX_WAIT_SECONDS, code, exc,
                )
                break

            logger.warning(
                "%s call hit a transient error (status %s); retry %d/%d in %.1fs: %s",
                schema_name, code, transient_retries, _MAX_TRANSIENT_RETRIES, delay, exc,
            )
            time.sleep(delay)
            continue

        try:
            content = response.content
            if not content:
                raise ValueError("Model returned empty content.")

            parsed = json.loads(content)
            if source_keys:
                if not isinstance(parsed, dict) or not all(
                    _is_string_list(parsed.get(k)) for k in source_keys
                ):
                    raise ValueError(
                        "Model did not return one JSON array of strings per source."
                    )
                parsed = {k: parsed[k] for k in source_keys}
            else:
                if isinstance(parsed, dict):
                    parsed = parsed.get("skills")
                if not _is_string_list(parsed):
                    raise ValueError("Model did not return a JSON array of strings.")

            usage = response.response_metadata.get("token_usage", {})
            if rate_limits:
                _WINDOW.append((time.monotonic(), usage.get("total_tokens") or est))
            details = usage.get("completion_tokens_details") or {}
            meta = {
                "task": task,
                "elapsed": time.monotonic() - start,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "attempts": attempts,
                "reasoning_tokens": details.get("reasoning_tokens"),
            }
            # One line per successful call: this is how you learn the real
            # per-resume token cost on the free tier.
            logger.info(
                "%s ok: task=%s prompt_tokens=%s completion_tokens=%s attempts=%d elapsed=%.2fs",
                schema_name, task, meta["prompt_tokens"], meta["completion_tokens"],
                attempts, meta["elapsed"],
            )
            return parsed, meta

        except (json.JSONDecodeError, ValueError, AttributeError) as exc:
            last_error = exc
            bad_output_retries += 1
            logger.warning(
                "%s call returned unusable output on attempt %d: %s",
                schema_name, attempts, exc,
            )
            if bad_output_retries > _RETRIES:
                break

    raise error_cls(
        f"Model did not return usable {schema_name} after {attempts} attempt(s): {last_error}"
    )