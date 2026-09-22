"""
Celery task for JD required-skills extraction.

Mirrors app/core/skills_extraction_tasks.py's run_skills_extraction_task,
with one structural difference: Job has no stored blob_path (unlike
Resume), so this task works off Job.jd_raw_text -- plain text already
extracted at upload time in app/api/routes/jobs.py's upload_jd() -- not
downloaded file bytes.

Kept as its own task, separate from any future resume-side retries or
failures, for the same isolation reason skills_extraction_tasks.py gives:
this can be re-run on its own (e.g. after a locator/prompt change)
without touching resume extraction at all.

locate_required_skills() is expected in app/core/jd_skills_locator.py
(not built here) with the contract:

    def locate_required_skills(jd_text: str) -> dict:
        # returns {"found": bool, "section_text": str, "heading": str | None}

See app/api/routes/jobs.py's upload_jd() for the trigger point.
"""

import logging
from datetime import datetime, timezone

from app.core.celery_app import celery_app
from app.core.jd_skills_locator import locate_required_skills
from app.core.jd_skills_llm_extract import JDSkillsExtractionError, extract_jd_skills_only
from app.core.skills_text_prep import (
    normalize_parentheses,
    postprocess_skills,
    strip_structural_labels,
)
from app.db.session import SessionLocal
from app.models.job import Job, JobExtractionStatus

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
            if not job.jd_raw_text or not job.jd_raw_text.strip():
                raise ValueError("Job has no extracted JD text to search.")

            located = locate_required_skills(job.jd_raw_text)

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

        except (ValueError, JDSkillsExtractionError) as exc:
            job.skills_extraction_status = JobExtractionStatus.FAILED
            job.skills_extraction_error = str(exc)
            db.commit()
            return

        except Exception as exc:
            logger.warning(
                "JD skills extraction failed for %s: %s",
                job_id, exc,
            )

            try:
                raise self.retry(exc=exc)

            except self.MaxRetriesExceededError:
                job.skills_extraction_status = JobExtractionStatus.FAILED
                job.skills_extraction_error = (
                    f"JD skills extraction failed after retries: {exc}"
                )
                db.commit()

            return

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
