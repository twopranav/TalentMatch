"""
Celery task for the standalone, separately-triggerable skills-only
extraction path.

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
from app.core.resume_storage import download_resume_blob
from app.core.skills_llm_extract import SkillsExtractionError, extract_skills_only
from app.core.skills_pdf_locator import locate_skills_section
from app.core.skills_text_prep import (
    normalize_parentheses,
    postprocess_skills,
    strip_leading_dates,
    strip_structural_labels,
)
from app.core.text_extract import EmptyExtractionError, UnsupportedFileTypeError
from app.db.session import SessionLocal
from app.models.resume import Resume, ResumeExtractionStatus

logger = logging.getLogger(__name__)


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

            located = locate_skills_section(file_bytes, resume.original_filename)

            if not located["found"] or not located["section_text"].strip():
                raise EmptyExtractionError(
                    "Could not locate a skills section in this resume."
                )

            # Order matters: dates are stripped from the still-cased,
            # still-grouped section text; normalize_parentheses then
            # lowercases and expands any "AWS (ECS, S3)" style grouping;
            # only after that do we strip bare category-label lines,
            # since a label can itself sit inside a now-expanded line.
            prepared = strip_leading_dates(located["section_text"])
            prepared = normalize_parentheses(prepared)
            prepared = strip_structural_labels(prepared)

            if not prepared.strip():
                raise EmptyExtractionError(
                    "Skills section was located but contained no usable text."
                )

            raw_skills = extract_skills_only(prepared)

            # Validate against `prepared` -- the exact text the model
            # saw -- not the original PDF text. See postprocess_skills'
            # docstring for why that distinction matters.
            skills, hallucinated, dupes_removed = postprocess_skills(
                raw_skills,
                source_text=prepared,
            )

            if hallucinated:
                logger.warning(
                    "Resume %s: dropped %d hallucinated skill(s) not "
                    "found in source: %s",
                    resume_id, len(hallucinated), hallucinated,
                )

            if dupes_removed:
                logger.info(
                    "Resume %s: removed %d exact duplicate skill(s).",
                    resume_id, dupes_removed,
                )

        except (
            UnsupportedFileTypeError,
            EmptyExtractionError,
            SkillsExtractionError,
        ) as exc:
            resume.skills_extraction_status = ResumeExtractionStatus.FAILED
            resume.skills_extraction_error = str(exc)
            db.commit()
            return

        except Exception as exc:
            logger.warning(
                "Skills extraction failed for %s: %s",
                resume_id, exc,
            )

            try:
                raise self.retry(exc=exc)

            except self.MaxRetriesExceededError:
                resume.skills_extraction_status = ResumeExtractionStatus.FAILED
                resume.skills_extraction_error = (
                    f"Skills extraction failed after retries: {exc}"
                )
                db.commit()

            return

        # -------------------------
        # Persist extraction
        # -------------------------

        resume.skills_result = skills
        resume.skills_section_heading = located["heading"]
        resume.skills_extraction_status = ResumeExtractionStatus.DONE
        resume.skills_extraction_error = None
        resume.skills_extracted_at = datetime.now(timezone.utc)

        db.commit()

    finally:
        db.close()