"""
Hugging Face Inference Providers-based structured extraction (Phase 4).
Two entry points: extract_candidate_profile() and
extract_job_requirements(). Replaces the earlier Ollama implementation —
see the .env.example / config.py diffs for the settings that moved.

Both are plain synchronous functions — the Celery task in
extraction_tasks.py wraps these unchanged; it doesn't reimplement
extraction logic. Keeping that separation is what let this swap happen
without touching resumes.py's extraction call site (only the import).
"""
import json
import logging
import time
from copy import deepcopy

from huggingface_hub import InferenceClient
from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError
from pydantic import ValidationError

from app.core.config import settings
from app.core.experience_calc import compute_experience_years
from app.schemas.extraction import CandidateProfileExtraction, JobRequirementsExtraction

logger = logging.getLogger(__name__)

# How long to wait on a single HF call before giving up on it. Without
# this, a hung provider hangs a Celery worker indefinitely (resumes) or —
# worse — the synchronous JD-upload request itself (jobs.py), since that
# path calls extract_job_requirements() inline in the request handler.
_HF_TIMEOUT_SECONDS = 30

_clients: dict[str, InferenceClient] = {}

def _get_client(provider: str) -> InferenceClient:
    if provider not in _clients:
        _clients[provider] = InferenceClient(
            provider=provider, api_key=settings.HF_TOKEN, timeout=_HF_TIMEOUT_SECONDS,
        )
    return _clients[provider]

class ExtractionError(Exception):
    """The provider's response couldn't be parsed/validated into the
    target schema, or the call to the provider itself failed in a way
    that a retry won't fix (bad auth, bad request, timeout after
    exhausting retries). The Celery task and the JD-upload route both
    catch this and mark the row 'failed' with the message — it does not
    crash the worker or 500 the request."""


_CANDIDATE_SYSTEM_PROMPT = """You extract structured data from resumes. \
Return only what the resume actually supports — do not invent, guess, or \
pad any field.

Field-specific rules:
- skills: named tools, languages, frameworks, platforms, or techniques \
mentioned anywhere in the resume (a skills section, a project \
description, a job bullet) — e.g. "Kubernetes", "PostgreSQL", "query \
optimization". Do NOT extract project names, team/company names, job \
titles, or paraphrased responsibilities as skills. A bullet saying "led \
schema migration for zero-downtime changes" is not itself a skill — only \
pull out an actual named technology mentioned within it, if any (here: \
none). When in doubt whether a phrase is a real named skill or just \
prose describing what someone did, leave it out. Use the resume's own \
wording for genuine skills, don't normalize or rename them.
- experience_years: leave this null. It is calculated separately from \
the work_history dates you return, not by you — put your effort into \
getting start_date/end_date exactly right for every entry instead \
(including writing "Present"/"Current" verbatim when a role is ongoing).
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


def _strict_json_schema(schema: dict) -> dict:
    """OpenAI-style strict structured output (what HF's providers
    implement) requires EVERY object in the schema graph — not just the
    top level — to list all its own properties as required and set
    additionalProperties: false. Pydantic's model_json_schema() only
    marks a property required at the top level when it has no default
    (every field here has one, so a partial document doesn't fail
    validation), and never touches nested $defs or array-item schemas at
    all.

    Left unpatched, an object with zero keys is already schema-valid,
    which let Ollama's local grammar (the old engine) stop after a
    couple of easy fields near the top of the resume. Some HF providers
    are worse here: instead of erroring on a non-strict nested schema,
    they silently fall back to unconstrained decoding — defeating the
    whole point of the retry-once reliability trick below. So this walks
    the entire schema (top level, every entry in $defs, and inside every
    array's 'items') and patches each object node in place.
    """
    schema = deepcopy(schema)

    def _patch(node: dict) -> None:
        if "properties" in node:
            node["required"] = list(node["properties"].keys())
            node["additionalProperties"] = False
            for prop_schema in node["properties"].values():
                _patch(prop_schema)
        if "items" in node:
            _patch(node["items"])

    _patch(schema)
    for def_schema in schema.get("$defs", {}).values():
        _patch(def_schema)
    return schema


def _call_hf(
    system_prompt: str,
    document_text: str,
    schema: dict,
    *,
    model: str | None = None,
    provider: str | None = None,
    retries: int = 1,
) -> tuple[dict, dict]:
    model = model or settings.HF_EXTRACTION_MODEL
    provider = provider or settings.HF_INFERENCE_PROVIDER
    client = _get_client(provider)
    strict_schema = _strict_json_schema(schema)
    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "extraction", "schema": strict_schema, "strict": True},
    }
    last_error: Exception | None = None
    start = time.monotonic()
    for attempt in range(retries + 1):
        try:
            response = client.chat_completion(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": document_text},
                ],
                response_format=response_format,
                temperature=0.1,
            )
        except HfHubHTTPError as e:
            last_error = e
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code is not None and 400 <= status_code < 500 and status_code != 429:
                # Bad auth, bad request, gated/unknown model — retrying with
                # the exact same call won't change the outcome. Fail fast
                # instead of burning the retry budget (and, for the Celery
                # path, Celery's own retry budget on top of this one).
                raise ExtractionError(
                    f"HF provider rejected the request ({status_code}), not retrying: {e}"
                ) from e
            logger.warning(
                "HF provider HTTP error on attempt %d/%d (status=%s): %s",
                attempt + 1, retries + 1, status_code, e,
            )
            continue
        except InferenceTimeoutError as e:
            last_error = e
            logger.warning(
                "HF provider timed out after %ss on attempt %d/%d",
                _HF_TIMEOUT_SECONDS, attempt + 1, retries + 1,
            )
            continue

        content = response.choices[0].message.content
        try:
            parsed = json.loads(content)
            usage = getattr(response, "usage", None)
            meta = {
                "model": model,
                "provider": provider,
                "elapsed": time.monotonic() - start,
                "prompt_tokens": getattr(usage, "prompt_tokens", None),
                "completion_tokens": getattr(usage, "completion_tokens", None),
            }
            return parsed, meta
        except json.JSONDecodeError as e:
            last_error = e
            logger.warning(
                "HF provider returned invalid JSON on attempt %d/%d: %s",
                attempt + 1, retries + 1, e,
            )
    raise ExtractionError(
        f"HF provider did not return a usable response after {retries + 1} attempt(s): {last_error}"
    )


def extract_candidate_profile(resume_text: str) -> CandidateProfileExtraction:
    raw, _ = _call_hf(
        _CANDIDATE_SYSTEM_PROMPT, resume_text,
        CandidateProfileExtraction.model_json_schema(),
    )
    try:
        profile = CandidateProfileExtraction.model_validate(raw)
    except ValidationError as e:
        raise ExtractionError(f"Response didn't match CandidateProfileExtraction: {e}")
    profile.experience_years = compute_experience_years(profile.work_history)
    return profile


def extract_job_requirements(jd_text: str) -> JobRequirementsExtraction:
    raw, _ = _call_hf(
        _JOB_SYSTEM_PROMPT, jd_text,
        JobRequirementsExtraction.model_json_schema(),
    )
    try:
        return JobRequirementsExtraction.model_validate(raw)
    except ValidationError as e:
        raise ExtractionError(f"Response didn't match JobRequirementsExtraction: {e}")

def _extract_candidate_profile_for_eval(
    resume_text: str, model: str, provider: str
) -> tuple[CandidateProfileExtraction, dict]:
    """eval_harness.py only. Same pipeline as extract_candidate_profile,
    but with model/provider overrides and metadata returned for
    side-by-side comparison. Not used by any request/Celery path."""
    raw, meta = _call_hf(
        _CANDIDATE_SYSTEM_PROMPT, resume_text,
        CandidateProfileExtraction.model_json_schema(),
        model=model, provider=provider,
    )
    profile = CandidateProfileExtraction.model_validate(raw)  # let ValidationError propagate — eval_harness reports it
    profile.experience_years = compute_experience_years(profile.work_history)
    return profile, meta

def _extract_job_requirements_for_eval(
    jd_text: str, model: str, provider: str
) -> tuple[JobRequirementsExtraction, dict]:
    """eval_harness.py only. See _extract_candidate_profile_for_eval."""
    raw, meta = _call_hf(
        _JOB_SYSTEM_PROMPT, jd_text,
        JobRequirementsExtraction.model_json_schema(),
        model=model, provider=provider,
    )
    return JobRequirementsExtraction.model_validate(raw), meta