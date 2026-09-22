"""
Hugging Face Inference Providers-based structured extraction.

Two entry points:
    extract_candidate_profile()
    extract_job_requirements()

The functions are synchronous by design. Celery wraps resume extraction
outside the request path, while JD extraction is currently executed from
the JD upload route through a threadpool.
"""

import json
import logging
import time
from copy import deepcopy

from huggingface_hub.errors import HfHubHTTPError, InferenceTimeoutError
from pydantic import ValidationError

from app.core.config import settings
from app.core.experience_calc import compute_experience_years
from app.core.hf_client import HF_TIMEOUT_SECONDS, get_client
from app.schemas.extraction import (
    CandidateProfileExtraction,
    JobRequirementsExtraction,
)

logger = logging.getLogger(__name__)

# Kept as an alias -- this module's own code below still refers to it by
# its original name in a couple of places (e.g. the timeout log message).
_HF_TIMEOUT_SECONDS = HF_TIMEOUT_SECONDS


class ExtractionError(Exception):
    """
    Raised when Hugging Face extraction fails or returns unusable data.

    The caller can safely mark the relevant extraction record as FAILED
    without crashing the request or Celery worker.
    """


_CANDIDATE_SYSTEM_PROMPT = """
You extract structured data from resumes.

Your task is EXTRACTION, not interpretation.

Return ONLY information supported by the resume.
Do not invent, guess, calculate, normalize, rename, or pad missing fields.

==================================================
GENERAL RULES
==================================================

1. Preserve the resume's own wording whenever practical.
2. Extract every clearly identifiable entry.
3. Do not delete an entry merely because it has incomplete details.
4. Use null for missing scalar information.
5. Use [] for genuinely absent list information.
6. Do not create plausible information to fill empty fields.
7. Do not infer information from dates when the resume explicitly states it.

==================================================
SKILLS
==================================================

Extract genuine technical skills mentioned anywhere in the resume.

Include:

- programming languages
- frameworks
- libraries
- databases
- cloud platforms
- infrastructure technologies
- developer tools
- testing technologies
- AI/ML technologies
- technical protocols
- concrete technical techniques or practices explicitly presented as skills

Examples:

Python
FastAPI
PostgreSQL
Kubernetes
Docker
Redis
AWS
REST APIs
SQL
pytest
query optimization

Do NOT extract:

- company names
- candidate names
- project names
- job titles
- generic personality traits
- generic business activities
- complete responsibility sentences
- arbitrary nouns from prose

For example:

"Designed schemas, migrations and idempotent endpoints."

Do not turn "idempotent endpoints" or "migrations" into arbitrary skills
unless the resume explicitly presents them as technical skills or named
technologies.

Likewise:

"Owned API layer for billing workflows."

Do not create "billing workflows" as a skill.

Preserve the resume's terminology.
Do not normalize or rename skills here.
Normalization happens later in the matching layer.

Avoid duplicates.

==================================================
STATED EXPERIENCE
==================================================

stated_experience:

Extract an explicit overall experience claim exactly or nearly exactly
as written.

Examples:

"5+ years"
"around seven years"
"8 years of experience"
"more than 6 years"

Do NOT calculate this field from work-history dates.

If the resume does not explicitly state a total experience amount,
return null.

experience_years:

ALWAYS leave this null during model extraction.

The application calculates it separately from work_history.

==================================================
EDUCATION
==================================================

Extract every clearly identifiable education entry.

Look for headings such as:

Education
Academic Background
Qualifications
Education & Certifications

For each entry extract:

- degree
- institution
- year

If the institution or year is absent, use null.

Do not invent institutions.

Do not discard an education entry merely because one field is missing.

Do not put certifications into education.

==================================================
CERTIFICATIONS
==================================================

Extract every explicit certification.

For each certification extract:

- name
- issuer
- year

Example:

"Azure Fundamentals — Microsoft — 2023"

becomes:

name = "Azure Fundamentals"
issuer = "Microsoft"
year = 2023

Use null when issuer/year is not stated.

Never invent issuer/year.

Return [] only when no certifications exist.

==================================================
WORK HISTORY
==================================================

Extract EVERY identifiable employment entry.

For each role extract:

- company
- title
- start_date
- end_date
- duration

Preserve dates as written.

Examples:

"2021—Now"
"2023 to Present"
"Aug 2020 - 2022"
"Jan 2024 – Present"

If the resume says "Present", preserve "Present".
If it says "Now", preserve "Now".

Do not convert a clearly stated date into null.

Do not append durations to start_date or end_date.

For example, do NOT produce:

start_date = "2018 (6 months)"

Instead:

start_date = "2018"
duration = "6 months"

Only populate duration when the resume explicitly states a duration.

Do not merge distinct employment entries.

Internships are valid work-history entries when they are presented as such.

==================================================
PROJECTS
==================================================

This field is IMPORTANT.

Actively look for project information.

Recognize headings such as:

Projects
Project Experience
Selected Projects
Key Projects
Academic Projects
Personal Projects
Professional Projects

Also recognize clearly named projects that appear outside a formal Projects
heading.

If a project name is identifiable, create a project entry.

A project does NOT need a long description.

Example:

Subscription API

must be extracted as a project even if its only associated text is:

Python, FastAPI, PostgreSQL, Redis, Docker

Likewise:

Legacy API migration

must be extracted even when the only detail is:

Flask → Go

For every project:

- name = actual project name
- description = supporting project text

Do not return [] when identifiable projects are present.

Return [] only when there is genuinely no project information.

==================================================
NAME / EMAIL
==================================================

candidate_name:
Extract only when literally present in the resume.

candidate_email:
Extract only when literally present in the resume.

Otherwise return null.

==================================================
EMPTY FIELDS
==================================================

Use:

[] for empty lists

null for missing scalar values

Never invent entries.

==================================================
FINAL RULE
==================================================

Return JSON matching the provided schema exactly.

No commentary.
No markdown.
No extra fields.
"""


_JOB_SYSTEM_PROMPT = """
You extract structured requirements from job descriptions.

Your task is EXTRACTION, not candidate ranking.

Return ONLY information supported by the JD.
Do not invent, guess, or infer mandatory status from your own judgment.

==================================================
TWO SKILL OUTPUTS
==================================================

There are two skill-related fields:

1. skills
2. compulsory_skills

skills:
All genuine technical skills and technical competencies mentioned anywhere
in the JD.

compulsory_skills:
ONLY skills that the JD explicitly identifies as mandatory, compulsory,
required, essential, or otherwise states that a candidate must possess.

A skill can appear in both lists.

Example:

Compulsory Skills:
Python
FastAPI
PostgreSQL
Docker

Elsewhere:
Redis
AWS
Kafka
pytest
CI/CD

Then:

skills:
Python, FastAPI, PostgreSQL, Docker, Redis, AWS, Kafka, pytest, CI/CD

compulsory_skills:
Python, FastAPI, PostgreSQL, Docker

Do NOT create a preferred_skills category.

==================================================
SKILLS
==================================================

Extract genuine technical skills mentioned anywhere in the JD.

Include:

- programming languages
- frameworks
- libraries
- databases
- cloud platforms
- infrastructure technologies
- testing technologies
- developer tools
- AI/ML technologies
- APIs/protocols
- technical methodologies
- concrete technical practices or competencies

Examples:

Python
FastAPI
PostgreSQL
Docker
Kubernetes
AWS
REST API
Redis
SQL
pytest
query optimization
schema design
authentication
authorization
observability
CI/CD

Do NOT extract:

- job titles
- company names
- location
- department
- salary
- generic personality traits
- complete responsibility sentences
- arbitrary business nouns

Example:

"Design and develop scalable REST APIs using Python and FastAPI."

Extract:

REST API
Python
FastAPI

Do NOT extract the complete sentence.

==================================================
ATOMIC SKILLS
==================================================

Prefer short noun phrases.

Good:

Python
FastAPI
PostgreSQL
query optimization
schema design
automated testing
CI/CD

Bad:

Design and develop scalable backend services
Strong experience designing APIs
Ability to build reliable distributed applications

Avoid sentence-like entries.

==================================================
LIST COVERAGE
==================================================

When the JD explicitly lists several technical items, extract every
genuine item.

Example:

"authentication, authorization, observability, caching, and distributed systems"

extract:

authentication
authorization
observability
caching
distributed systems

Do not stop after the first one or two.

==================================================
COMPULSORY SKILLS
==================================================

Only place a skill into compulsory_skills when the JD explicitly identifies
it as mandatory.

Strong signals include:

- Compulsory Skills
- Mandatory Skills
- Required Skills
- Must have
- Required:
- Candidates must have
- You must have
- Essential skills
- X is mandatory
- required experience with X

Example:

Compulsory Skills:
Python
FastAPI
PostgreSQL
Docker

All four belong in compulsory_skills.

If the JD merely mentions:

"We also use Redis, AWS and Kafka."

Then these belong in skills only.

Do NOT make them compulsory.

==================================================
DO NOT INFER MANDATORY STATUS
==================================================

Do not decide that something is mandatory because it seems important.

Do not treat every technology in responsibilities as mandatory.

Do not treat every technology in the JD as mandatory.

Mandatory status must be explicitly supported by the JD language.

==================================================
EXPERIENCE
==================================================

Extract only explicitly stated numeric requirements.

Examples:

"6–12 years"
min = 6
max = 12

"5+ years"
min = 5
max = null

"At least 4 years"
min = 4
max = null

"3 years of experience"
min = 3
max = 3

No explicit number:
min = null
max = null

Do not infer experience from seniority.

==================================================
EDUCATION
==================================================

Extract the most specific explicit education requirement.

Example:

"Bachelor's degree in Computer Science, Engineering, or a related field,
or equivalent practical experience"

Return that text.

If no education requirement is stated, return null.

Do not invent a degree.

==================================================
EMPTY FIELDS
==================================================

Use [] for empty lists.
Use null for missing scalar fields.

==================================================
FINAL RULE
==================================================

Return JSON matching the schema exactly.

No commentary.
No markdown.
No extra fields.
"""


def _strict_json_schema(schema: dict) -> dict:
    """
    Patch the full schema graph for strict structured decoding.

    Every object must:
    - require all declared properties
    - reject additional properties

    This includes nested $defs and array item objects.
    """
    schema = deepcopy(schema)

    def _patch(node: dict) -> None:
        if not isinstance(node, dict):
            return

        if "properties" in node:
            node["required"] = list(node["properties"].keys())
            node["additionalProperties"] = False

            for prop_schema in node["properties"].values():
                _patch(prop_schema)

        if "items" in node:
            _patch(node["items"])

        if "$defs" in node:
            for def_schema in node["$defs"].values():
                _patch(def_schema)

    _patch(schema)

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
    """
    Execute one structured Hugging Face inference request.

    Retries transient provider failures and malformed JSON.
    Fails fast on non-retryable 4xx errors.
    """
    model = model or settings.HF_EXTRACTION_MODEL
    provider = provider or settings.HF_INFERENCE_PROVIDER

    client = get_client(provider)

    strict_schema = _strict_json_schema(schema)

    response_format = {
        "type": "json_schema",
        "json_schema": {
            "name": "extraction",
            "schema": strict_schema,
            "strict": True,
        },
    }

    last_error: Exception | None = None
    start = time.monotonic()

    for attempt in range(retries + 1):
        try:
            response = client.chat_completion(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": document_text,
                    },
                ],
                response_format=response_format,
                temperature=0.1,
            )

        except HfHubHTTPError as exc:
            last_error = exc

            status_code = getattr(
                getattr(exc, "response", None),
                "status_code",
                None,
            )

            if (
                status_code is not None
                and 400 <= status_code < 500
                and status_code != 429
            ):
                raise ExtractionError(
                    f"HF provider rejected the request "
                    f"({status_code}), not retrying: {exc}"
                ) from exc

            logger.warning(
                "HF provider HTTP error on attempt %d/%d "
                "(status=%s): %s",
                attempt + 1,
                retries + 1,
                status_code,
                exc,
            )
            continue

        except InferenceTimeoutError as exc:
            last_error = exc

            logger.warning(
                "HF provider timed out after %ss on attempt %d/%d",
                _HF_TIMEOUT_SECONDS,
                attempt + 1,
                retries + 1,
            )
            continue

        except Exception as exc:
            last_error = exc

            logger.warning(
                "Unexpected HF extraction error on attempt %d/%d: %s",
                attempt + 1,
                retries + 1,
                exc,
            )
            continue

        try:
            content = response.choices[0].message.content

            if not content:
                raise ValueError("HF provider returned empty content.")

            parsed = json.loads(content)

            usage = getattr(response, "usage", None)

            meta = {
                "model": model,
                "provider": provider,
                "elapsed": time.monotonic() - start,
                "prompt_tokens": getattr(
                    usage,
                    "prompt_tokens",
                    None,
                ),
                "completion_tokens": getattr(
                    usage,
                    "completion_tokens",
                    None,
                ),
            }

            return parsed, meta

        except (json.JSONDecodeError, ValueError, AttributeError, IndexError) as exc:
            last_error = exc

            logger.warning(
                "HF provider returned unusable structured output "
                "on attempt %d/%d: %s",
                attempt + 1,
                retries + 1,
                exc,
            )

    raise ExtractionError(
        "HF provider did not return a usable response after "
        f"{retries + 1} attempt(s): {last_error}"
    )


def extract_candidate_profile(
    resume_text: str,
) -> CandidateProfileExtraction:
    if not resume_text or not resume_text.strip():
        raise ExtractionError("Resume text is empty.")

    raw, _ = _call_hf(
        _CANDIDATE_SYSTEM_PROMPT,
        resume_text,
        CandidateProfileExtraction.model_json_schema(),
    )

    try:
        profile = CandidateProfileExtraction.model_validate(raw)
    except ValidationError as exc:
        raise ExtractionError(
            f"Response did not match CandidateProfileExtraction: {exc}"
        ) from exc

    # The model extracts the source statement, while the application
    # derives the numeric value from work history.
    profile.experience_years = compute_experience_years(
        profile.work_history
    )

    return profile


def extract_job_requirements(
    jd_text: str,
) -> JobRequirementsExtraction:
    if not jd_text or not jd_text.strip():
        raise ExtractionError("Job description text is empty.")

    raw, _ = _call_hf(
        _JOB_SYSTEM_PROMPT,
        jd_text,
        JobRequirementsExtraction.model_json_schema(),
    )

    try:
        return JobRequirementsExtraction.model_validate(raw)
    except ValidationError as exc:
        raise ExtractionError(
            f"Response did not match JobRequirementsExtraction: {exc}"
        ) from exc


def _extract_candidate_profile_for_eval(
    resume_text: str,
    model: str,
    provider: str,
) -> tuple[CandidateProfileExtraction, dict]:
    """
    Evaluation-only variant with model/provider overrides.
    """
    raw, meta = _call_hf(
        _CANDIDATE_SYSTEM_PROMPT,
        resume_text,
        CandidateProfileExtraction.model_json_schema(),
        model=model,
        provider=provider,
    )

    profile = CandidateProfileExtraction.model_validate(raw)

    profile.experience_years = compute_experience_years(
        profile.work_history
    )

    return profile, meta


def _extract_job_requirements_for_eval(
    jd_text: str,
    model: str,
    provider: str,
) -> tuple[JobRequirementsExtraction, dict]:
    """
    Evaluation-only variant with model/provider overrides.
    """
    raw, meta = _call_hf(
        _JOB_SYSTEM_PROMPT,
        jd_text,
        JobRequirementsExtraction.model_json_schema(),
        model=model,
        provider=provider,
    )

    return JobRequirementsExtraction.model_validate(raw), meta