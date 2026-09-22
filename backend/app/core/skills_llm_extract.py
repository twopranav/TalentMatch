"""
Standalone skill-decomposition LLM call.

Deliberately separate from llm_extract.extract_candidate_profile(): that
call asks one large model to pull an entire candidate profile (skills,
work history, education, projects...) out of the whole resume in a
single structured-decode pass. This call does exactly one narrow thing:
given text that skills_pdf_locator.py already narrowed down to "this is
the Skills section", turn it into a clean JSON array of individual skill
strings, following the strict copy/split/no-invent rules in
app/prompts/skills_extraction_prompt.txt (adapted from the standalone
prompt.txt used with run-test.py / score.py during prompt development --
see those files for how the prompt itself was iterated on and scored
against gold.json).

Kept as its own module -- with its own Celery task and its own trigger
route -- rather than folded into extract_candidate_profile() so that:

- it can be retried, re-run, or rate-limited independently of full
  profile extraction (a resume whose full profile already succeeded
  doesn't need to redo that call just to pick up a prompt change here,
  and vice versa)
- HF_SKILLS_MODEL/HF_SKILLS_PROVIDER can point at a different, e.g.
  cheaper or faster, model for this narrow task without touching
  HF_EXTRACTION_MODEL/HF_INFERENCE_PROVIDER used by the profile call
- a prompt or model change here can be evaluated with score.py without
  needing eval_harness.py's full-profile schema at all
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
    Path(__file__).resolve().parents[1] / "prompts" / "skills_extraction_prompt.txt"
)
_SKILLS_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# Forces the HF structured-decode endpoint to emit a bare JSON array of
# strings (mirrors SKILLS_SCHEMA in run-test.py), so the model can't
# drift into returning an object or a nested structure.
_SKILLS_JSON_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
}


class SkillsExtractionError(Exception):
    """
    Raised when the standalone skills call fails or returns unusable
    data. The caller marks the resume's skills_extraction_status FAILED
    without crashing the Celery worker -- same convention as
    llm_extract.ExtractionError.
    """


def _call_hf_skills(document_text: str) -> tuple[list[str], dict]:
    model = settings.HF_SKILLS_MODEL or settings.HF_EXTRACTION_MODEL
    provider = settings.HF_SKILLS_PROVIDER or settings.HF_INFERENCE_PROVIDER

    client = get_client(provider)

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "skills",
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
                    {"role": "system", "content": _SKILLS_SYSTEM_PROMPT},
                    {"role": "user", "content": document_text},
                ],
                response_format=response_format,
                temperature=0,
            )

        except HfHubHTTPError as exc:
            last_error = exc

            status_code = getattr(getattr(exc, "response", None), "status_code", None)

            if status_code is not None and 400 <= status_code < 500 and status_code != 429:
                raise SkillsExtractionError(
                    f"HF provider rejected the skills request "
                    f"({status_code}), not retrying: {exc}"
                ) from exc

            logger.warning(
                "HF skills call HTTP error on attempt %d/%d (status=%s): %s",
                attempt + 1, _RETRIES + 1, status_code, exc,
            )
            continue

        except InferenceTimeoutError as exc:
            last_error = exc

            logger.warning(
                "HF skills call timed out after %ss on attempt %d/%d",
                HF_TIMEOUT_SECONDS, attempt + 1, _RETRIES + 1,
            )
            continue

        except Exception as exc:
            last_error = exc

            logger.warning(
                "Unexpected HF skills extraction error on attempt %d/%d: %s",
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
                "HF skills call returned unusable output on attempt %d/%d: %s",
                attempt + 1, _RETRIES + 1, exc,
            )

    raise SkillsExtractionError(
        f"HF provider did not return usable skills after "
        f"{_RETRIES + 1} attempt(s): {last_error}"
    )


def extract_skills_only(prepared_text: str) -> list[str]:
    """
    prepared_text must already be through skills_text_prep's cleanup
    (strip_leading_dates -> normalize_parentheses -> strip_structural_labels).

    Returns the raw list the model produced, BEFORE
    skills_text_prep.postprocess_skills() -- callers apply that
    themselves so they can log/inspect what got dropped as
    hallucinated or duplicate.
    """
    if not prepared_text or not prepared_text.strip():
        raise SkillsExtractionError("Skills section text is empty.")

    skills, _meta = _call_hf_skills(prepared_text)
    return skills