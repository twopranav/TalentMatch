"""
Fault handling for the skills-only extraction pipelines: finds rows
stuck at PENDING (task never ran -- worker was down, message dropped)
or sitting at FAILED, and redispatches them, without requiring a
re-upload.

Two independent periodic tasks, not one shared sweep, deliberately --
same isolation rationale as everywhere else in this pipeline (see
skills_extraction_tasks.py / jd_skills_extraction_tasks.py's module
docstrings): a bug in the resume sweep query should never be able to
starve or crash the JD sweep, and vice versa.

Capped retries: skills_extraction_retry_count on each row is
incremented only here, never by the extraction task itself on a normal
run. Once a row hits MAX_AUTO_RETRIES, the sweep leaves it alone --
something about that specific file is probably wrong (corrupt PDF, no
skills section at all, a provider that will never accept this input),
and blindly redispatching it forever wastes HF calls for no gain. At
that point it needs either a human to look at skills_extraction_error,
or the candidate/recruiter to re-upload.

PENDING rows get a stale window (STALE_PENDING_AFTER) before being
considered abandoned, not swept immediately: a row that was PENDING
30 seconds ago most likely just hasn't been picked up by a worker yet,
not dropped. Neither model has a per-extraction-attempt timestamp
(only the general updated_at, which any field change bumps), so
updated_at is used as a proxy -- imprecise if something else on the
row was edited in the meantime, but a false-negative here just delays
a retry by one more sweep interval rather than causing harm.

Register both tasks' periods in celery_app.py's beat_schedule; run a
beat process alongside the worker:
    celery -A app.core.celery_app beat --loglevel=info
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.jd_skills_extraction_tasks import run_jd_skills_extraction_task
from app.core.skills_extraction_tasks import run_skills_extraction_task
from app.db.session import SessionLocal
from app.models.job import Job, JobExtractionStatus
from app.models.resume import Resume, ResumeExtractionStatus

logger = logging.getLogger(__name__)

MAX_AUTO_RETRIES = 3
STALE_PENDING_AFTER = timedelta(minutes=10)


@celery_app.task(name="extraction_retry_sweep.sweep_resumes")
def sweep_stale_resume_skills_extractions() -> None:
    db = SessionLocal()

    try:
        cutoff = datetime.now(timezone.utc) - STALE_PENDING_AFTER

        stuck_pending = db.scalars(
            select(Resume).where(
                Resume.skills_extraction_status == ResumeExtractionStatus.PENDING,
                Resume.updated_at < cutoff,
                Resume.skills_extraction_retry_count < MAX_AUTO_RETRIES,
            )
        ).all()

        failed = db.scalars(
            select(Resume).where(
                Resume.skills_extraction_status == ResumeExtractionStatus.FAILED,
                Resume.skills_extraction_retry_count < MAX_AUTO_RETRIES,
            )
        ).all()

        candidates = stuck_pending + failed

        if not candidates:
            return

        logger.info(
            "Resume skills sweep: redispatching %d row(s) "
            "(%d stale-pending, %d failed).",
            len(candidates), len(stuck_pending), len(failed),
        )

        for resume in candidates:
            resume.skills_extraction_retry_count += 1
            resume.skills_extraction_status = ResumeExtractionStatus.PENDING
            db.commit()

            run_skills_extraction_task.delay(str(resume.id))

    finally:
        db.close()


@celery_app.task(name="extraction_retry_sweep.sweep_jobs")
def sweep_stale_job_skills_extractions() -> None:
    db = SessionLocal()

    try:
        cutoff = datetime.now(timezone.utc) - STALE_PENDING_AFTER

        stuck_pending = db.scalars(
            select(Job).where(
                Job.skills_extraction_status == JobExtractionStatus.PENDING,
                Job.updated_at < cutoff,
                Job.skills_extraction_retry_count < MAX_AUTO_RETRIES,
                # A brand-new job that has never had a JD uploaded is
                # also skills_extraction_status=PENDING by default (see
                # the Job model) -- that's not a dropped task, there is
                # nothing to extract. Only sweep rows that actually have
                # JD text to work from.
                Job.jd_raw_text.is_not(None),
            )
        ).all()

        failed = db.scalars(
            select(Job).where(
                Job.skills_extraction_status == JobExtractionStatus.FAILED,
                Job.skills_extraction_retry_count < MAX_AUTO_RETRIES,
            )
        ).all()

        candidates = stuck_pending + failed

        if not candidates:
            return

        logger.info(
            "JD skills sweep: redispatching %d row(s) "
            "(%d stale-pending, %d failed).",
            len(candidates), len(stuck_pending), len(failed),
        )

        for job in candidates:
            job.skills_extraction_retry_count += 1
            job.skills_extraction_status = JobExtractionStatus.PENDING
            db.commit()

            run_jd_skills_extraction_task.delay(str(job.id))

    finally:
        db.close()