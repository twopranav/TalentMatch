"""
Shared retry/parse/validate machinery behind the two standalone
skills-extraction calls (skills_llm_extract.py, jd_skills_llm_extract.py).
Kept separate from those two files so each keeps its own exception type,
prompt, and llm_configs task -- a resume-skills failure or model change
can never get confused with a JD-skills one.

Two different kinds of failure are retried, on separate budgets:

  * Transient (rate limit 429, timeout, 5xx): the call never produced an
    answer. Wait, then retry -- honouring the provider's retry-after hint.
    If the provider asks for a wait longer than _MAX_WAIT_SECONDS we give up
    immediately instead of parking a worker; the caller marks the resume
    FAILED and the retry sweep / a manual re-run picks it up later.
  * Bad output (empty, not JSON, wrong shape): the model answered, badly.
    Re-ask once, no waiting.

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


def call_skills_model(
    *,
    task: str,
    system_prompt: str,
    document_text: str,
    schema_name: str,
    error_cls: type[Exception],
) -> tuple[list[str], dict]:
    llm = get_chat_model_for_task(task).bind(
        response_format={
            "type": "json_schema",
            "json_schema": {"name": schema_name, "schema": _SKILLS_JSON_SCHEMA, "strict": True},
        }
    )

    last_error: Exception | None = None
    start = time.monotonic()
    attempts = 0
    transient_retries = 0
    bad_output_retries = 0

    while True:
        attempts += 1

        try:
            response = llm.invoke(
                [
                    {"role": "system", "content": system_prompt + _OUTPUT_FORMAT_NOTE},
                    {"role": "user", "content": document_text},
                ]
            )
        except Exception as exc:
            last_error = exc
            code = _status_code(exc)

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
            if isinstance(parsed, dict):
                parsed = parsed.get("skills")
            if not isinstance(parsed, list) or not all(isinstance(i, str) for i in parsed):
                raise ValueError("Model did not return a JSON array of strings.")

            usage = response.response_metadata.get("token_usage", {})
            meta = {
                "task": task,
                "elapsed": time.monotonic() - start,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "attempts": attempts,
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