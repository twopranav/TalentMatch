"""
Celery tasks that compute Application.match_score.

    score_application_task(application_id)
        resume (skills + experience_months) vs job (skills + min months)
        -> semantic_match.compute_match -> written onto the Application row.

Triggers (all best-effort; the sweep below is the safety net):
    * candidate applies                      -> routes/applications.apply_to_job
    * a JD's skills extraction finishes      -> dispatch_score_for_job()
    * a resume's skills extraction finishes  -> dispatch_score_for_resume()
    * recruiter hits POST /applications/job/{id}/rescore

Readiness: an application can only be scored once BOTH sides are DONE. If
one side is still extracting, the row stays 'pending' and returns; the
extraction task that finishes later re-triggers scoring. If a side FAILED,
the row is marked 'failed' with a readable reason, and is rescored
automatically if that side is later re-extracted successfully.

Nothing is filtered out: a score of 0 is still a score.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.dispatch import dispatch_extraction
from app.core.embeddings import EmbeddingError, embed
from app.core.llm_provider_registry import LLMConfigError
from app.core.semantic_match import MatchWeights, compute_match
from app.db.session import SessionLocal
from app.models.application import Application
from app.models.job import Job, JobExtractionStatus
from app.models.resume import Resume, ResumeExtractionStatus

logger = logging.getLogger(__name__)

STALE_PENDING_AFTER = timedelta(minutes=10)


def _weights() -> MatchWeights:
    return MatchWeights(
        skills=settings.MATCH_WEIGHT_SKILLS,
        experience=settings.MATCH_WEIGHT_EXPERIENCE,
        sim_low=settings.MATCH_SIM_LOW,
        sim_high=settings.MATCH_SIM_HIGH,
    )


def _fail(db, application, reason: str) -> None:
    application.match_status = "failed"
    application.match_error = reason
    db.commit()


@celery_app.task(
    name="match.score_application",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def score_application_task(self, application_id: str) -> None:
    db = SessionLocal()
    try:
        application = db.get(Application, application_id)
        if application is None:
            logger.warning("score_application_task: application %s is gone", application_id)
            return

        resume = db.get(Resume, application.resume_id) if application.resume_id else None
        job = db.get(Job, application.job_id)

        if resume is None:
            return _fail(db, application, "Application has no resume to score.")
        if job is None:
            return  # cascade-deleted underneath us

        # --- readiness -------------------------------------------------
        if resume.skills_extraction_status == ResumeExtractionStatus.FAILED:
            return _fail(db, application, "The resume's skills could not be extracted.")
        if job.skills_extraction_status == JobExtractionStatus.FAILED:
            return _fail(db, application, "The job description's skills could not be extracted.")
        if (
            resume.skills_extraction_status != ResumeExtractionStatus.DONE
            or job.skills_extraction_status != JobExtractionStatus.DONE
        ):
            application.match_status = "pending"
            db.commit()
            return  # the extraction task that finishes later re-triggers us
        if not job.skills_result:
            return _fail(db, application, "The job description has no extracted skills to match against.")

        # --- score -----------------------------------------------------
        try:
            result = compute_match(
                resume_skills=resume.skills_result,
                resume_months=resume.experience_months,
                jd_skills=job.skills_result,
                jd_min_months=job.min_experience_months,
                embed=embed,
                weights=_weights(),
            )
        except LLMConfigError as exc:
            return _fail(db, application, str(exc))
        except EmbeddingError as exc:
            if self.request.retries >= self.max_retries:
                return _fail(db, application, f"Scoring failed after retries: {exc}")
            logger.warning("Scoring %s attempt failed: %s", application_id, exc)
            raise self.retry(exc=exc, countdown=30 * 2 ** self.request.retries)

        application.match_score = result.score
        application.match_details = result.to_dict()
        application.match_status = "done"
        application.match_error = None
        application.matched_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Fan-out helpers. Take the caller's session so they can run inside another
# task's transaction scope; failures are the caller's to swallow (best-effort).
# ---------------------------------------------------------------------------

def _dispatch_ids(ids) -> int:
    n = 0
    for application_id in ids:
        if dispatch_extraction(score_application_task, application_id):
            n += 1
    return n


def dispatch_score_for_job(db, job_id) -> int:
    ids = db.scalars(select(Application.id).where(Application.job_id == job_id)).all()
    return _dispatch_ids(ids)


def dispatch_score_for_resume(db, resume_id) -> int:
    ids = db.scalars(select(Application.id).where(Application.resume_id == resume_id)).all()
    return _dispatch_ids(ids)


@celery_app.task(name="match.sweep")
def sweep_unscored_applications() -> None:
    """Re-dispatch applications stuck at 'pending' although both sides are
    ready (dispatch happened while Redis was down, or the message was lost)."""
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - STALE_PENDING_AFTER
        ids = db.scalars(
            select(Application.id)
            .join(Resume, Resume.id == Application.resume_id)
            .join(Job, Job.id == Application.job_id)
            .where(
                Application.match_status == "pending",
                Application.updated_at < cutoff,
                Resume.skills_extraction_status == ResumeExtractionStatus.DONE,
                Job.skills_extraction_status == JobExtractionStatus.DONE,
            )
        ).all()
        if ids:
            logger.info("Match sweep: redispatching %d application(s).", len(ids))
            _dispatch_ids(ids)
    finally:
        db.close()


def safe_dispatch_for_job(db, job_id) -> None:
    """Called at the end of a JD extraction task. Must never fail it."""
    try:
        dispatch_score_for_job(db, job_id)
    except Exception:
        logger.warning("Could not queue rescoring for job %s; sweep will catch up.", job_id, exc_info=True)


def safe_dispatch_for_resume(db, resume_id) -> None:
    """Called at the end of a resume extraction task. Must never fail it."""
    try:
        dispatch_score_for_resume(db, resume_id)
    except Exception:
        logger.warning("Could not queue rescoring for resume %s; sweep will catch up.", resume_id, exc_info=True)
