"""
Celery task for the standalone, separately-triggerable skills-only
extraction path. Reads three sources from the resume -- Skills section,
Work Experience, Projects -- and stores skills per source plus one
merged list (Resume.skills_result) for matching.

Deliberately NOT called from inside extraction_tasks.run_extraction_task
(full profile extraction). Keeping them as two independent tasks means:

- triggering one never blocks on, retries because of, or gets marked
  FAILED by a failure in the other
- this path can be re-run on its own (e.g. after a prompt or
  section-locator change) without re-running the full HF profile call
  for every resume

See app/api/routes/resumes.py's POST /resumes/{resume_id}/extract-skills
for the trigger point, and app/core/skills_pdf_locator.py /
app/core/skills_llm_extract.py / app/core/skills_text_prep.py for the
three stages this task chains together.
"""

import logging
from datetime import datetime, timezone

from app.core.celery_app import celery_app
from app.core.experience_calc import extract_resume_experience
from app.core.resume_storage import download_resume_blob
from app.core.skills_llm_extract import SkillsExtractionError, extract_skills_by_source
from app.core.skills_pdf_locator import locate_resume_sections
from app.core.skills_text_prep import (
    SOURCE_KEYS,
    build_skill_blocks,
    fill_source_occurrences,
    merge_source_skills,
    postprocess_skills,
    reroute_leaks,
)
from app.core.text_extract import (
    EmptyExtractionError,
    UnsupportedFileTypeError,
    extract_text_from_bytes,
    )
from app.db.session import SessionLocal
from app.models.resume import Resume, ResumeExtractionStatus
from app.core.llm_provider_registry import LLMConfigError
from app.core.matching_tasks import safe_dispatch_for_resume

logger = logging.getLogger(__name__)


def _store_experience(resume: Resume, file_bytes: bytes) -> None:
    """Deterministic work-experience extraction, computed right after the
    file is downloaded and BEFORE the skills-section check, so a resume
    with no locatable skills section still gets its experience (the
    FAILED-path commit persists it, same as the JD task). Never raises:
    experience is independent of skills and must not fail or retry it."""
    try:
        text = extract_text_from_bytes(file_bytes, resume.original_filename)
        result = extract_resume_experience(text)
    except Exception:
        logger.exception(
            "Resume %s: experience extraction failed; skills extraction continues.",
            resume.id,
        )
        return

    resume.experience_months = result.months
    resume.experience_entries = [
        e.model_dump(exclude={"duration"}) for e in result.entries
    ]


@celery_app.task(
    name="skills_extraction.run",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run_skills_extraction_task(self, resume_id: str) -> None:
    db = SessionLocal()

    try:
        resume = db.get(Resume, resume_id)

        if resume is None:
            logger.warning(
                "run_skills_extraction_task: resume %s no longer exists",
                resume_id,
            )
            return

        resume.skills_extraction_status = ResumeExtractionStatus.PROCESSING
        resume.skills_extraction_error = None
        db.commit()

        try:
            file_bytes = download_resume_blob(resume.blob_path)
            _store_experience(resume, file_bytes)
            located = locate_resume_sections(file_bytes, resume.original_filename)

            # Deterministic prep per source (see build_skill_blocks for the
            # skills-block cleanup order). A resume with no skills section
            # can still be extracted from its experience / projects.
            blocks = build_skill_blocks(located)

            if not any(blocks.values()):
                raise EmptyExtractionError(
                    "Could not locate a skills, experience or projects "
                    "section in this resume."
                )

            raw = extract_skills_by_source(blocks)

            # A skill the model filed under the wrong source moves to the
            # block it literally appears in; then each list is validated
            # against the exact text the model saw for that block -- not
            # the original PDF text. See postprocess_skills' docstring
            # for why that distinction matters.
            routed = reroute_leaks(raw, blocks)
            by_source: dict[str, list[str]] = {}

            for key in SOURCE_KEYS:
                by_source[key], hallucinated, dupes_removed = postprocess_skills(
                    routed[key],
                    source_text=blocks[key],
                )

                if hallucinated:
                    logger.warning(
                        "Resume %s: dropped %d hallucinated skill(s) from %s "
                        "not found in source: %s",
                        resume_id, len(hallucinated), key, hallucinated,
                    )

                if dupes_removed:
                    logger.info(
                        "Resume %s: removed %d exact duplicate skill(s) from %s.",
                        resume_id, dupes_removed, key,
                    )

            # The model works block by block and can miss a skill's second or
            # third home. Add it wherever it literally appears, so each list
            # holds every skill mentioned in that section -- scoring weighs a
            # skill by the best section it shows up in.
            by_source = fill_source_occurrences(by_source, blocks)

            skills = merge_source_skills(by_source)

        except (
            UnsupportedFileTypeError,
            EmptyExtractionError,
            SkillsExtractionError,
            LLMConfigError,
        ) as exc:
            resume.skills_extraction_status = ResumeExtractionStatus.FAILED
            resume.skills_extraction_error = str(exc)
            db.commit()
            safe_dispatch_for_resume(db, resume_id)
            return

        except Exception as exc:
            if self.request.retries >= self.max_retries:
                resume.skills_extraction_status = ResumeExtractionStatus.FAILED
                resume.skills_extraction_error = (
                    f"Skills extraction failed after retries: {exc}"
                )
                db.commit()
                return

            logger.warning(
                "Skills extraction attempt failed for %s: %s", resume_id, exc
            )
            resume.skills_extraction_status = ResumeExtractionStatus.PENDING
            db.commit()
            raise self.retry(exc=exc, countdown=30 * 2 ** self.request.retries)

        # -------------------------
        # Persist extraction
        # -------------------------

        resume.skills_result = skills
        resume.skills_by_source = by_source
        resume.skills_section_heading = located["skills"]["heading"]
        resume.skills_extraction_status = ResumeExtractionStatus.DONE
        resume.skills_extraction_error = None
        resume.skills_extracted_at = datetime.now(timezone.utc)

        db.commit()

        # Applications pointing at this resume can now be (re)scored.
        safe_dispatch_for_resume(db, resume_id)

    finally:
        db.close()