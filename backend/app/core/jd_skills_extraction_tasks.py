"""
Celery task for JD required-skills extraction.

Mirrors app/core/skills_extraction_tasks.py's run_skills_extraction_task.
Dispatched by app/api/routes/jobs.py's upload_jd() after the row (and the
stored file's blob_path) is committed; this task is the "event queue ->
LLM" leg: it downloads the stored JD file, locates the required-skills
section, cleans it, calls the narrow LLM extractor, and validates the
result.

Locating uses app/core/jd_skills_locator.locate_jd_requirements(), which
dispatches on file type (column-aware for PDFs, flat text for DOCX/TXT).
If a job somehow has no stored file (legacy rows uploaded before blob
storage existed), it falls back to scanning Job.jd_raw_text.

Kept as its own task, separate from resume-side retries or failures, for
the same isolation reason skills_extraction_tasks.py gives: it can be
re-run on its own (e.g. after a locator/prompt change) without touching
resume extraction at all.
"""

import logging
from datetime import datetime, timezone

from app.core.celery_app import celery_app
from app.core.jd_skills_locator import locate_jd_requirements, locate_required_skills
from app.core.jd_skills_llm_extract import JDSkillsExtractionError, extract_jd_skills_only
from app.core.resume_storage import download_resume_blob
from app.core.skills_text_prep import (
    normalize_parentheses,
    postprocess_skills,
    strip_structural_labels,
)
from app.core.text_extract import EmptyExtractionError, UnsupportedFileTypeError
from app.db.session import SessionLocal
from app.models.job import Job, JobExtractionStatus
from app.core.llm_provider_registry import LLMConfigError

logger = logging.getLogger(__name__)


@celery_app.task(
    name="jd_skills_extraction.run",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def run_jd_skills_extraction_task(self, job_id: str) -> None:
    db = SessionLocal()

    try:
        job = db.get(Job, job_id)

        if job is None:
            logger.warning(
                "run_jd_skills_extraction_task: job %s no longer exists",
                job_id,
            )
            return

        job.skills_extraction_status = JobExtractionStatus.PROCESSING
        job.skills_extraction_error = None
        db.commit()

        try:
            if job.blob_path:
                file_bytes = download_resume_blob(job.blob_path)
                located = locate_jd_requirements(
                    file_bytes, job.original_filename or ""
                )
            elif job.jd_raw_text and job.jd_raw_text.strip():
                located = locate_required_skills(job.jd_raw_text)
            else:
                raise ValueError("Job has no stored JD file or extracted text.")

            if not located["found"] or not located["section_text"].strip():
                raise ValueError(
                    "Could not locate a required-skills section in this JD."
                )

            # Order matches skills_text_prep's documented order for the
            # resume pipeline, minus strip_leading_dates -- JD
            # required-skills sections don't carry embedded dates the
            # way resume skills-under-a-role sections sometimes do.
            prepared = normalize_parentheses(located["section_text"])
            prepared = strip_structural_labels(prepared)

            if not prepared.strip():
                raise ValueError(
                    "Required-skills section was located but contained "
                    "no usable text."
                )

            raw_skills = extract_jd_skills_only(prepared)

            # Validate against `prepared` -- the exact text the model
            # saw -- not the original JD text. See postprocess_skills'
            # docstring for why that distinction matters.
            skills, hallucinated, dupes_removed = postprocess_skills(
                raw_skills,
                source_text=prepared,
            )

            if hallucinated:
                logger.warning(
                    "Job %s: dropped %d hallucinated skill(s) not "
                    "found in source: %s",
                    job_id, len(hallucinated), hallucinated,
                )

            if dupes_removed:
                logger.info(
                    "Job %s: removed %d exact duplicate skill(s).",
                    job_id, dupes_removed,
                )

        except (
            ValueError,
            JDSkillsExtractionError,
            UnsupportedFileTypeError,
            EmptyExtractionError,
            LLMConfigError,
        ) as exc:
            job.skills_extraction_status = JobExtractionStatus.FAILED
            job.skills_extraction_error = str(exc)
            db.commit()
            return

        except Exception as exc:
            if self.request.retries >= self.max_retries:
                job.skills_extraction_status = JobExtractionStatus.FAILED
                job.skills_extraction_error = (
                    f"JD skills extraction failed after retries: {exc}"
                )
                db.commit()
                return

            logger.warning(
                "JD skills extraction attempt failed for %s: %s", job_id, exc
            )
            job.skills_extraction_status = JobExtractionStatus.PENDING
            db.commit()
            raise self.retry(exc=exc, countdown=30 * 2 ** self.request.retries)

        # -------------------------
        # Persist extraction
        # -------------------------

        job.skills_result = skills
        job.skills_section_heading = located["heading"]
        job.skills_extraction_status = JobExtractionStatus.DONE
        job.skills_extraction_error = None
        job.skills_extracted_at = datetime.now(timezone.utc)

        db.commit()

    finally:
        db.close()