"""
Shared retry/parse/validate machinery behind the two standalone
skills-extraction calls (skills_llm_extract.py, jd_skills_llm_extract.py).
Kept separate from those two files so each keeps its own exception type,
prompt, and llm_configs task -- a resume-skills failure or model change
can never get confused with a JD-skills one.
"""

import json
import logging
import time

from app.core.llm_client import get_chat_model_for_task

logger = logging.getLogger(__name__)

_RETRIES = 1

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

    for attempt in range(_RETRIES + 1):
        try:
            response = llm.invoke(
                [
                    {"role": "system", "content": system_prompt + _OUTPUT_FORMAT_NOTE},
                    {"role": "user", "content": document_text},
                ]
            )
        except Exception as exc:
            # TODO: narrow this once you've seen what a timeout vs. a 4xx
            # actually looks like coming through ChatOpenAI in your logs --
            # LangChain re-wraps provider errors rather than passing the
            # old provider-specific exception types through.
            last_error = exc
            logger.warning(
                "%s call failed on attempt %d/%d: %s",
                schema_name, attempt + 1, _RETRIES + 1, exc,
            )
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
            }
            return parsed, meta

        except (json.JSONDecodeError, ValueError, AttributeError) as exc:
            last_error = exc
            logger.warning(
                "%s call returned unusable output on attempt %d/%d: %s",
                schema_name, attempt + 1, _RETRIES + 1, exc,
            )

    raise error_cls(
        f"Model did not return usable {schema_name} after {_RETRIES + 1} attempt(s): {last_error}"
    )