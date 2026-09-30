"""
Standalone skill-decomposition LLM call for job descriptions.

Mirrors app/core/skills_llm_extract.py exactly, but reads
app/prompts/jd_skills_extraction_prompt.txt and is kept as its own
module/exception type so a JD extraction failure never gets confused
with, or retried alongside, a resume skills extraction failure -- same
isolation rationale as the resume pipeline (see
skills_extraction_tasks.py's module docstring). Its provider/model
(llm_configs task="jd_skills") can be swapped from the admin UI
independently of the resume_skills task.

Input is plain text (locate_required_skills() operates on
Job.jd_raw_text, not PDF bytes -- Job has no stored blob_path, unlike
Resume), already narrowed down to "this is the required-skills section"
and run through jd_text_prep's cleanup.
"""

import logging
from pathlib import Path

from app.core.llm_json_call import call_skills_model

logger = logging.getLogger(__name__)

_PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "jd_skills_extraction_prompt.txt"
)
_JD_SKILLS_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


class JDSkillsExtractionError(Exception):
    """
    Raised when the standalone JD skills call fails or returns unusable
    data. The caller marks the job's skills_extraction_status FAILED
    without crashing the Celery worker -- same convention as
    skills_llm_extract.SkillsExtractionError.
    """


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

    skills, _meta = call_skills_model(
        task="jd_skills",
        system_prompt=_JD_SKILLS_SYSTEM_PROMPT,
        document_text=prepared_text,
        schema_name="jd_skills",
        error_cls=JDSkillsExtractionError,
    )
    return skills
