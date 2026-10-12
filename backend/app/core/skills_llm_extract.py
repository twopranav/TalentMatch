"""
Standalone skill-decomposition LLM call.

Given the three text blocks that skills_pdf_locator.py located and
skills_text_prep.build_skill_blocks() cleaned (skills section, work
experience, projects), turn them into one clean list of individual
skill strings per source, following the strict copy/split/no-invent
rules in app/prompts/skills_extraction_prompt.txt (iterated and scored
against a gold answer key in the resume_extraction notebook).

Kept as its own module -- with its own Celery task and its own trigger
route -- rather than folded into a full-profile extraction call so that
it can be retried, re-run, or rate-limited independently, and its
provider/model (llm_configs task="resume_skills") can be swapped from
the admin UI without touching the JD skills task.
"""

import logging
from pathlib import Path

from app.core.config import settings
from app.core.llm_json_call import call_skills_model
from app.core.skills_text_prep import SOURCE_KEYS

logger = logging.getLogger(__name__)

_PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "skills_extraction_prompt.txt"
)
_SKILLS_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")

# Same run settings as the JD call (jd_skills_llm_extract.py): low reasoning
# so reasoning models don't burn their output budget before writing the JSON,
# and a client-side throttle so bulk uploads don't hit the provider's TPM limit.
# The registry drops any override the active model doesn't support.
_RESUME_MODEL_OVERRIDES = {"reasoning_effort": "low", "max_tokens": 4000, "timeout": 60}
_RESUME_RATE_LIMITS = (settings.LLM_RPM_LIMIT, settings.LLM_TPM_LIMIT)  # (RPM, TPM)

# Marker line that introduces each block in the user message; the prompt
# describes these exact strings.
_MARKERS = {
    "skills_section": "===SKILLS SECTION===",
    "work_experience": "===WORK EXPERIENCE===",
    "projects": "===PROJECTS===",
}


class SkillsExtractionError(Exception):
    """
    Raised when the standalone skills call fails or returns unusable
    data. The caller marks the resume's skills_extraction_status FAILED
    without crashing the Celery worker.
    """


def extract_skills_by_source(blocks: dict[str, str]) -> dict[str, list[str]]:
    """
    blocks must come from skills_text_prep.build_skill_blocks() (keys =
    SOURCE_KEYS; "" for a source that wasn't located, sent as "(none)").

    Returns the raw per-source lists the model produced, BEFORE
    skills_text_prep.reroute_leaks() / postprocess_skills() -- callers
    apply those themselves so they can log/inspect what got moved or
    dropped as hallucinated or duplicate.
    """
    if not any((blocks.get(k) or "").strip() for k in SOURCE_KEYS):
        raise SkillsExtractionError("Skills, experience and projects text are all empty.")

    user_text = "\n".join(
        f"{_MARKERS[k]}\n{(blocks.get(k) or '').strip() or '(none)'}" for k in SOURCE_KEYS
    )

    skills, _meta = call_skills_model(
        task="resume_skills",
        system_prompt=_SKILLS_SYSTEM_PROMPT,
        document_text=user_text,
        schema_name="skills",
        error_cls=SkillsExtractionError,
        source_keys=SOURCE_KEYS,
        model_overrides=_RESUME_MODEL_OVERRIDES,
        rate_limits=_RESUME_RATE_LIMITS,
    )
    return skills
