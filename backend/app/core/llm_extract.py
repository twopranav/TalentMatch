"""
Ollama-based structured extraction (Phase 4). Two entry points:
extract_candidate_profile() and extract_job_requirements().

Both are plain synchronous functions — no Celery here on purpose. This is
the piece to hand-test against real resumes/JDs before any async plumbing
goes around it (see eval_extraction.py). The Celery task wraps these
unchanged; it doesn't reimplement extraction logic.
"""
import json
import logging

from ollama import Client
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.extraction import CandidateProfileExtraction, JobRequirementsExtraction

logger = logging.getLogger(__name__)

_client = Client(host=settings.OLLAMA_HOST)


class ExtractionError(Exception):
    """Ollama's response couldn't be parsed/validated into the target
    schema, even after a retry. The Celery task catches this and marks
    the row 'failed' with the message — it does not crash the worker."""


# Schema-constrained decoding (the `format` dict below) guarantees valid
# JSON *shape*. It does not guarantee the model read the document
# correctly — that's what these prompts are for.

_CANDIDATE_SYSTEM_PROMPT = """You extract structured data from resumes. \
Return only what the resume actually supports — do not invent, guess, or \
pad any field.

Field-specific rules:
- skills: every skill explicitly named anywhere in the resume (a skills \
section, a project description, a job bullet). Use the resume's own \
wording, don't normalize or rename them.
- experience_years: compute this from the date ranges in work_history \
(sum the distinct employment periods, don't double-count overlaps). Do \
not state a number that disagrees with the work_history dates you also \
return. If there is no work history at all, return null, not 0.
- education / certifications / projects / work_history: return an empty \
list [] if the resume has none — never invent a plausible-looking entry \
to fill the field.
- candidate_name / candidate_email: only if literally present in the \
text (usually near the top). Otherwise null.

Return JSON matching the given schema exactly, with no extra commentary."""

_JOB_SYSTEM_PROMPT = """You extract structured requirements from job \
descriptions. Return only what the JD actually states.

Field-specific rules:
- required_skills vs preferred_skills: this distinction is about the \
JD's own language, not your judgment of what's important. Phrases like \
"must have", "required", "X+ years of Y" with no hedge -> required. \
Phrases like "nice to have", "bonus", "preferred", "a plus" -> preferred. \
If the JD doesn't distinguish (just lists skills with no qualifying \
language), put them all in required_skills and leave preferred_skills \
empty — don't guess which ones the employer would consider optional.
- min_experience_years / max_experience_years: only if the JD states a \
number or range. "5+ years" -> min=5, max=null. "3-5 years" -> min=3, \
max=5. No stated number -> both null.
- education_requirement: the literal requirement stated (e.g. "Bachelor's \
in Computer Science or related field"), or null if none is stated.

Return JSON matching the given schema exactly, with no extra commentary."""


def _call_ollama(system_prompt: str, document_text: str, schema: dict, retries: int = 1) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        response = _client.chat(
            model=settings.OLLAMA_EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": document_text},
            ],
            format=schema,
            # Low, not default (Ollama's default of 0.7 is tuned for
            # conversational variety, which is the opposite of what you
            # want from repeated structured extraction).
            options={"temperature": 0.1},
        )
        try:
            return json.loads(response.message.content)
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(
                "Ollama returned invalid JSON on attempt %d/%d: %s",
                attempt + 1, retries + 1, e,
            )
    raise ExtractionError(
        f"Ollama did not return valid JSON after {retries + 1} attempt(s): {last_error}"
    )


def extract_candidate_profile(resume_text: str) -> CandidateProfileExtraction:
    raw = _call_ollama(
        _CANDIDATE_SYSTEM_PROMPT, resume_text,
        CandidateProfileExtraction.model_json_schema(),
    )
    try:
        return CandidateProfileExtraction.model_validate(raw)
    except ValidationError as e:
        raise ExtractionError(f"Response didn't match CandidateProfileExtraction: {e}")


def extract_job_requirements(jd_text: str) -> JobRequirementsExtraction:
    raw = _call_ollama(
        _JOB_SYSTEM_PROMPT, jd_text,
        JobRequirementsExtraction.model_json_schema(),
    )
    try:
        return JobRequirementsExtraction.model_validate(raw)
    except ValidationError as e:
        raise ExtractionError(f"Response didn't match JobRequirementsExtraction: {e}")