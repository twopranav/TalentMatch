from fastapi import HTTPException, status
from sqlalchemy import and_, false, true

from app.models.application import Application, ApplicationStatus, InterviewStage, ShortlistStage
from app.models.job import Job
from app.models.user import User, UserRole


def _same_company(user: User, job: Job) -> bool:
    return user.sub_company is not None and job.sub_company == user.sub_company


def can_read_job(user: User, job: Job) -> bool:
    """Superuser: every job. Admin and recruiter: every job in their own sub
    company, nothing outside it."""
    if user.role == UserRole.SUPERUSER:
        return True
    if user.role in (UserRole.ADMIN, UserRole.RECRUITER):
        return _same_company(user, job)
    return False


def can_write_job(user: User, job: Job) -> bool:
    """Superuser: every job. Admin: every job in their sub company.
    Recruiter: only jobs they posted, and only while the job is still in
    their sub company (so a recruiter moved to another sub company cannot
    keep editing jobs they left behind)."""
    if user.role == UserRole.SUPERUSER:
        return True
    if user.role == UserRole.ADMIN:
        return _same_company(user, job)
    return user.role == UserRole.RECRUITER and job.created_by_id == user.id and _same_company(user, job)


def job_read_clause(user: User):
    """SQL condition for 'jobs this user may read'."""
    if user.role == UserRole.SUPERUSER:
        return true()
    if user.role in (UserRole.ADMIN, UserRole.RECRUITER) and user.sub_company is not None:
        return Job.sub_company == user.sub_company
    return false()


def applicant_resume_job_clause(user: User):
    """SQL condition for 'jobs whose applicants' resumes this user may open'.

    Superuser: every job. Admin: every job in their sub company. Recruiter:
    only jobs they posted (and still in their sub company) -- i.e. only their
    own candidates, even though they can read the other applicants in the
    sub company. Anyone else: nothing.
    """
    if user.role == UserRole.SUPERUSER:
        return true()
    if user.sub_company is None:
        return false()
    if user.role == UserRole.ADMIN:
        return Job.sub_company == user.sub_company
    if user.role == UserRole.RECRUITER:
        return and_(Job.created_by_id == user.id, Job.sub_company == user.sub_company)
    return false()


def can_open_applicant_resume(user: User, job: Job) -> bool:
    """Python mirror of applicant_resume_job_clause (same rule as can_write_job)."""
    return can_write_job(user, job)


def assert_read_job(job: Job, user: User) -> None:
    if not can_read_job(user, job):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to view these applications")


def assert_write_job(job: Job, user: User) -> None:
    if not can_write_job(user, job):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have permission to change this job's applications")


def same_sub_company(actor: User, target: User) -> bool:
    """Superuser: any user. Admin: only users of their own sub company."""
    if actor.role == UserRole.SUPERUSER:
        return True
    return actor.sub_company is not None and target.sub_company == actor.sub_company


def apply_status_change(application: Application, new_status: ApplicationStatus) -> None:
    """Sub-state bookkeeping shared by the single and bulk status endpoints."""
    if new_status == application.status:
        return
    application.shortlist_stage = ShortlistStage.SHORTLISTED if new_status == ApplicationStatus.SHORTLISTED else None
    application.interview_at = None
    application.interview_stage = InterviewStage.SCHEDULED if new_status == ApplicationStatus.INTERVIEWING else None
    application.status = new_status
