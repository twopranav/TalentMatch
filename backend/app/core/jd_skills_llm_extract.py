"""
Standalone skill-decomposition LLM call for job descriptions.

Mirrors app/core/skills_llm_extract.py exactly, but reads
app/prompts/jd_skills_extraction_prompt.txt and is kept as its own
module/exception type so a JD extraction failure never gets confused
with, or retried alongside, a resume skills extraction failure -- same
isolation rationale as the resume pipeline (see
skills_extraction_tasks.py's module docstring).

Input is plain text (locate_required_skills() operates on
Job.jd_raw_text, not PDF bytes -- Job has no stored blob_path, unlike
Resume), already narrowed down to "this is the required-skills section"
and run through jd_text_prep's cleanup.
"""

import json
import logging
import time
from pathlib import Path

from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError

from app.core.config import settings
from app.core.hf_client import HF_TIMEOUT_SECONDS, get_client

logger = logging.getLogger(__name__)

_RETRIES = 1

_PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "jd_skills_extraction_prompt.txt"
)
_JD_SKILLS_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

_SKILLS_JSON_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
}


class JDSkillsExtractionError(Exception):
    """
    Raised when the standalone JD skills call fails or returns unusable
    data. The caller marks the job's skills_extraction_status FAILED
    without crashing the Celery worker -- same convention as
    skills_llm_extract.SkillsExtractionError.
    """


def _call_hf_jd_skills(document_text: str) -> tuple[list[str], dict]:
    model = settings.HF_SKILLS_MODEL or settings.HF_EXTRACTION_MODEL
    provider = settings.HF_SKILLS_PROVIDER or settings.HF_INFERENCE_PROVIDER

    client = get_client(provider)

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "jd_skills",
            "schema": _SKILLS_JSON_SCHEMA,
            "strict": True,
        },
    }

    last_error: Exception | None = None
    start = time.monotonic()

    for attempt in range(_RETRIES + 1):
        try:
            response = client.chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": _JD_SKILLS_SYSTEM_PROMPT},
                    {"role": "user", "content": document_text},
                ],
                response_format=response_format,
                temperature=0,
            )

        except HfHubHTTPError as exc:
            last_error = exc

            status_code = getattr(getattr(exc, "response", None), "status_code", None)

            if status_code is not None and 400 <= status_code < 500 and status_code != 429:
                raise JDSkillsExtractionError(
                    f"HF provider rejected the JD skills request "
                    f"({status_code}), not retrying: {exc}"
                ) from exc

            logger.warning(
                "HF JD skills call HTTP error on attempt %d/%d (status=%s): %s",
                attempt + 1, _RETRIES + 1, status_code, exc,
            )
            continue

        except InferenceTimeoutError as exc:
            last_error = exc

            logger.warning(
                "HF JD skills call timed out after %ss on attempt %d/%d",
                HF_TIMEOUT_SECONDS, attempt + 1, _RETRIES + 1,
            )
            continue

        except Exception as exc:
            last_error = exc

            logger.warning(
                "Unexpected HF JD skills extraction error on attempt %d/%d: %s",
                attempt + 1, _RETRIES + 1, exc,
            )
            continue

        try:
            content = response.choices[0].message.content

            if not content:
                raise ValueError("HF provider returned empty content.")

            parsed = json.loads(content)

            if not isinstance(parsed, list) or not all(
                isinstance(item, str) for item in parsed
            ):
                raise ValueError("HF provider did not return a JSON array of strings.")

            usage = getattr(response, "usage", None)

            meta = {
                "model": model,
                "provider": provider,
                "elapsed": time.monotonic() - start,
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
            }

            return parsed, meta

        except (json.JSONDecodeError, ValueError, AttributeError, IndexError) as exc:
            last_error = exc

            logger.warning(
                "HF JD skills call returned unusable output on attempt %d/%d: %s",
                attempt + 1, _RETRIES + 1, exc,
            )

    raise JDSkillsExtractionError(
        f"HF provider did not return usable JD skills after "
        f"{_RETRIES + 1} attempt(s): {last_error}"
    )


def extract_jd_skills_only(prepared_text: str) -> list[str]:
    """
    prepared_text must already be through jd_text_prep's cleanup
    (normalize_parentheses -> strip_structural_labels).

    Returns the raw list the model produced, BEFORE
    postprocess_skills() -- callers apply that themselves so they can
    log/inspect what got dropped as hallucinated or duplicate.
    """
    if not prepared_text or not prepared_text.strip():
        raise JDSkillsExtractionError("Required-skills section text is empty.")

    skills, _meta = _call_hf_jd_skills(prepared_text)
    return skills
