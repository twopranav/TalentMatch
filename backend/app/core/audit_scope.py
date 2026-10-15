"""SQL conditions that limit audit_logs rows to what a given role may see.

Shared by the audit route (api/routes/audit.py) and the admin overview feed
(api/routes/overview.py) so both always apply the same rule.

  * superuser: no condition (everything).
  * admin: only rows about their own sub company -- its jobs, the applications
    and notes on those jobs, and the users who belong to it. Resume rows are
    never included: the resume library is private to each person, so even
    its audit trail stays out of an admin's feed.
  * recruiter: only rows about jobs they own (see recruiter_scope).
"""
from sqlalchemy import String, and_, cast, false, func, or_, select
from sqlalchemy.orm import aliased

from app.models.audit_log import AuditLog
from app.models.job import Job
from app.models.user import User

# Audit rows that belong to a job via a job_id inside their JSON snapshot.
JOB_SCOPED_TYPES = ("application", "application_note")


def job_ref(model):
    """The job id (as text) stored in a row's snapshot. `after` is empty on a
    delete and `before` is empty on a create, so take whichever exists."""
    return func.coalesce(model.after["job_id"].astext, model.before["job_id"].astext)


def _snap(model, key: str):
    return func.coalesce(model.after[key].astext, model.before[key].astext)


def recruiter_scope(user: User):
    """SQL condition limiting audit rows to this recruiter's jobs.

    "Their jobs" is the jobs they own now PLUS jobs they once owned: a deleted
    job is gone from the jobs table, but its audit rows must stay visible, so
    ownership is also recovered from the audit trail (the job's snapshot
    carries created_by_id).
    """
    live_jobs = select(cast(Job.id, String)).where(Job.created_by_id == user.id)
    job_audit = aliased(AuditLog)  # separate alias so it isn't confused with the outer query
    ever_owned_jobs = select(cast(job_audit.resource_id, String)).where(
        job_audit.resource_type == "job",
        _snap(job_audit, "created_by_id") == str(user.id),
    )

    def mine(job_id_text):
        return or_(job_id_text.in_(live_jobs), job_id_text.in_(ever_owned_jobs))

    return or_(
        # The job's own audit rows: its resource_id IS the job id.
        and_(AuditLog.resource_type == "job", mine(cast(AuditLog.resource_id, String))),
        # Applications / notes: the job id is inside the snapshot.
        and_(AuditLog.resource_type.in_(JOB_SCOPED_TYPES), mine(job_ref(AuditLog))),
    )


def admin_scope(user: User):
    """SQL condition limiting audit rows to this admin's sub company.

    Default-deny: an admin with no sub company, and any resource type not
    listed here (resumes included), matches nothing.
    """
    if user.sub_company is None:
        return false()
    company = user.sub_company.value  # snapshots store the enum's value

    live_jobs = select(cast(Job.id, String)).where(Job.sub_company == user.sub_company)
    job_audit = aliased(AuditLog)
    # Deleted jobs are gone from the jobs table; recover their sub company
    # from the job's own audit snapshot.
    ever_in_company = select(cast(job_audit.resource_id, String)).where(
        job_audit.resource_type == "job",
        _snap(job_audit, "sub_company") == company,
    )

    def in_company(job_id_text):
        return or_(job_id_text.in_(live_jobs), job_id_text.in_(ever_in_company))

    return or_(
        and_(AuditLog.resource_type == "job", _snap(AuditLog, "sub_company") == company),
        and_(AuditLog.resource_type.in_(JOB_SCOPED_TYPES), in_company(job_ref(AuditLog))),
        and_(AuditLog.resource_type == "user", _snap(AuditLog, "sub_company") == company),
    )
