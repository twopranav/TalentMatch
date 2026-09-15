"""
One-off backfill for Phase 4 extraction (no new API surface — run manually).

Existing resumes/jobs were never touched by the extraction pipeline: it
only ever runs inline at upload time (see app/api/routes/resumes.py and
app/api/routes/jobs.py), so any row created before that code existed sits
at extraction_status=PENDING forever with no automatic retry. This script
walks those rows once and runs the exact same extraction logic the upload
routes use, so results end up identical to what a fresh upload would have
produced.

Requires HF_TOKEN set (see app/core/config.py / .env.example — the
Hugging Face Inference Providers token used by app/core/llm_extract.py).
Safe to re-run: only PENDING rows are picked up by default, so a row
already DONE or FAILED is left alone unless you pass --retry-failed.

Usage:
    python backfill_extraction.py resumes
    python backfill_extraction.py jobs
    python backfill_extraction.py all
    python backfill_extraction.py all --retry-failed
    python backfill_extraction.py all --dry-run
"""
import argparse
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.llm_extract import ExtractionError, extract_candidate_profile, extract_job_requirements
from app.core.resume_storage import download_resume_blob
from app.core.text_extract import EmptyExtractionError, UnsupportedFileTypeError, extract_text_from_bytes
from app.db.session import SessionLocal
from app.models.job import Job, JobExtractionStatus
from app.models.resume import Resume, ResumeExtractionStatus

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_extraction")


def _run_resume_extraction(resume: Resume) -> None:
    """Mirrors _run_extraction() in app/api/routes/resumes.py exactly —
    same fields written, same is_sourced rule for candidate_name/email —
    so a backfilled row is indistinguishable from a fresh upload."""
    try:
        file_bytes = download_resume_blob(resume.blob_path)
    except Exception as exc:
        resume.extraction_status = ResumeExtractionStatus.FAILED
        resume.extraction_error = f"Could not read stored file: {exc}"
        return

    try:
        text = extract_text_from_bytes(file_bytes, resume.original_filename)
        profile = extract_candidate_profile(text)
    except (UnsupportedFileTypeError, EmptyExtractionError, ExtractionError) as exc:
        resume.extraction_status = ResumeExtractionStatus.FAILED
        resume.extraction_error = str(exc)
        return
    except Exception as exc:  # belt-and-suspenders — see the matching comment in jobs.py
        logger.warning("Resume extraction failed for %s: %s", resume.original_filename, exc)
        resume.extraction_status = ResumeExtractionStatus.FAILED
        resume.extraction_error = f"Extraction failed: {exc}"
        return

    resume.raw_text = text
    resume.extracted_skills = profile.skills
    resume.extracted_experience_years = profile.experience_years
    resume.extracted_education = [e.model_dump() for e in profile.education]
    resume.extracted_certifications = profile.certifications
    resume.extracted_profile = profile.model_dump()
    resume.extraction_status = ResumeExtractionStatus.DONE
    resume.extracted_at = datetime.now(timezone.utc)

    # Same rule as the upload route: only sourced (no-account) resumes get
    # candidate_name/email filled in from extraction.
    if resume.owner_id is None:
        resume.candidate_name = profile.candidate_name
        resume.candidate_email = profile.candidate_email


def _run_job_extraction(job: Job) -> None:
    """Mirrors the extraction block in upload_jd() in
    app/api/routes/jobs.py. jd_raw_text is already stored on the row (no
    blob to fetch — jobs don't keep the original file), so this only
    needs to re-run the structured extraction step."""
    try:
        requirements = extract_job_requirements(job.jd_raw_text)
    except ExtractionError as exc:
        job.extraction_status = JobExtractionStatus.FAILED
        job.extraction_error = str(exc)
        return
    except Exception as exc:  # belt-and-suspenders — see the matching comment in jobs.py
        logger.warning("JD extraction failed for job %s: %s", job.id, exc)
        job.extraction_status = JobExtractionStatus.FAILED
        job.extraction_error = f"Extraction failed: {exc}"
        return

    job.extracted_required_skills = requirements.required_skills
    job.extracted_min_experience_years = requirements.min_experience_years
    job.extracted_max_experience_years = requirements.max_experience_years
    job.extracted_education_requirement = requirements.education_requirement
    job.extracted_profile = requirements.model_dump()
    job.extraction_status = JobExtractionStatus.DONE
    job.extracted_at = datetime.now(timezone.utc)


def backfill_resumes(db, statuses: list[ResumeExtractionStatus], dry_run: bool) -> None:
    resumes = db.scalars(
        select(Resume).where(Resume.extraction_status.in_(statuses))
    ).all()
    logger.info("Found %d resume(s) to process.", len(resumes))
    for i, resume in enumerate(resumes, 1):
        logger.info("[%d/%d] resume %s (%s)", i, len(resumes), resume.id, resume.original_filename)
        if dry_run:
            continue
        _run_resume_extraction(resume)
        db.commit()  # commit per-row so one failure/crash doesn't lose prior progress
        logger.info("  -> %s", resume.extraction_status.value)


def backfill_jobs(db, statuses: list[JobExtractionStatus], dry_run: bool) -> None:
    jobs = db.scalars(
        select(Job).where(Job.extraction_status.in_(statuses), Job.jd_raw_text.is_not(None))
    ).all()
    logger.info("Found %d job(s) to process.", len(jobs))
    for i, job in enumerate(jobs, 1):
        logger.info("[%d/%d] job %s (%s)", i, len(jobs), job.id, job.title)
        if dry_run:
            continue
        _run_job_extraction(job)
        db.commit()
        logger.info("  -> %s", job.extraction_status.value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", choices=["resumes", "jobs", "all"])
    parser.add_argument("--retry-failed", action="store_true", help="Also re-attempt rows currently marked FAILED, not just PENDING.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be processed without calling the HF API or writing anything.")
    args = parser.parse_args()

    resume_statuses = [ResumeExtractionStatus.PENDING] + (
        [ResumeExtractionStatus.FAILED] if args.retry_failed else []
    )
    job_statuses = [JobExtractionStatus.PENDING] + (
        [JobExtractionStatus.FAILED] if args.retry_failed else []
    )

    db = SessionLocal()
    try:
        if args.target in ("resumes", "all"):
            backfill_resumes(db, resume_statuses, args.dry_run)
        if args.target in ("jobs", "all"):
            backfill_jobs(db, job_statuses, args.dry_run)
    finally:
        db.close()


if __name__ == "__main__":
    main()