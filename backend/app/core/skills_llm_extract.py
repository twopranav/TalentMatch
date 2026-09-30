"""
Standalone skill-decomposition LLM call.

Given text that skills_pdf_locator.py already narrowed down to "this is
the Skills section", turn it into a clean JSON array of individual skill
strings, following the strict copy/split/no-invent rules in
app/prompts/skills_extraction_prompt.txt (adapted from the standalone
prompt.txt used with run-test.py / score.py during prompt development --
see those files for how the prompt itself was iterated on and scored
against gold.json).

Kept as its own module -- with its own Celery task and its own trigger
route -- rather than folded into a full-profile extraction call so that
it can be retried, re-run, or rate-limited independently, and its
provider/model (llm_configs task="resume_skills") can be swapped from
the admin UI without touching the JD skills task.
"""

import logging
from pathlib import Path

from app.core.llm_json_call import call_skills_model

logger = logging.getLogger(__name__)

_PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "skills_extraction_prompt.txt"
)
_SKILLS_SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")


class SkillsExtractionError(Exception):
    """
    Raised when the standalone skills call fails or returns unusable
    data. The caller marks the resume's skills_extraction_status FAILED
    without crashing the Celery worker.
    """


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

    skills, _meta = call_skills_model(
        task="resume_skills",
        system_prompt=_SKILLS_SYSTEM_PROMPT,
        document_text=prepared_text,
        schema_name="skills",
        error_cls=SkillsExtractionError,
    )
    return skills
