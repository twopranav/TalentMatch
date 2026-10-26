"""Role-scoped aggregate dashboard endpoint (GET /api/overview).

Every number comes from a GROUP BY / aggregate query, never from loading
rows and counting them in Python. The per-role payload is selected by the
caller's role; response shape is `{"role": ..., ...}`.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, false, func, select
from sqlalchemy.orm import Session

from app.core import metrics
from app.core.audit_scope import admin_scope
from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.application import Application, ApplicationStatus, ShortlistStage, InterviewStage
from app.models.audit_log import AuditLog
from app.models.job import Job, JobStatus
from app.models.llm_config import LLMConfig
from app.models.resume import Resume
from app.models.user import User, UserRole

router = APIRouter()


def _key(value) -> str:
    return str(value.value if hasattr(value, "value") else value)


def _applicant_overview(db: Session, user: User, now: datetime) -> dict:
    resume_counts = {
        _key(k): n
        for k, n in db.query(Resume.status, func.count(Resume.id))
        .filter(Resume.owner_id == user.id, Resume.is_archived.is_(False))
        .group_by(Resume.status)
        .all()
    }
    app_counts = {
        _key(k): n
        for k, n in db.query(Application.status, func.count(Application.id))
        .filter(Application.user_id == user.id)
        .group_by(Application.status)
        .all()
    }
    has_resume = sum(resume_counts.values()) > 0
    profile_complete = bool(user.full_name and user.phone)
    has_applied = sum(app_counts.values()) > 0

    interviews = (
        db.query(Application, Job.title)
        .join(Job, Job.id == Application.job_id)
        .filter(
            Application.user_id == user.id,
            Application.interview_stage == InterviewStage.SCHEDULED,
            Application.interview_at >= now,
        )
        .order_by(Application.interview_at.asc())
        .limit(10)
        .all()
    )
    recent = (
        db.query(Application, Job.title)
        .join(Job, Job.id == Application.job_id)
        .filter(Application.user_id == user.id)
        .order_by(Application.applied_at.desc())
        .limit(5)
        .all()
    )
    newest = (
        db.query(Job)
        .filter(Job.status == JobStatus.PUBLISHED)
        .order_by(Job.created_at.desc())
        .limit(5)
        .all()
    )
    # Deliberately no match_score / notes anywhere in this payload.
    return {
        "role": "applicant",
        "resume_status_counts": resume_counts,
        "onboarding": {"profile_complete": profile_complete, "has_resume": has_resume},
        "onboarding_checklist": [
            {"key": "complete_profile", "label": "Complete your profile", "done": profile_complete},
            {"key": "upload_resume", "label": "Upload a resume", "done": has_resume},
            {"key": "apply_to_job", "label": "Apply to a job", "done": has_applied},
        ],
        "application_status_counts": app_counts,
        "upcoming_interviews": [
            {
                "application_id": str(a.id),
                "job_id": str(a.job_id),
                "job_title": title,
                "interview_at": a.interview_at,
                "stage": _key(a.shortlist_stage),
            }
            for a, title in interviews
        ],
        "recent_applications": [
            {
                "id": str(a.id),
                "job_id": str(a.job_id),
                "job_title": title,
                "status": _key(a.status),
                "applied_at": a.applied_at,
            }
            for a, title in recent
        ],
        "newest_jobs": [
            {"id": str(j.id), "title": j.title, "location": j.location, "created_at": j.created_at}
            for j in newest
        ],
    }


def _recruiter_overview(db: Session, user: User, now: datetime) -> dict:
    own_job_ids = select(Job.id).where(Job.created_by_id == user.id)

    # One grouped query for every per-job counter.
    per_job = {
        row.job_id: row
        for row in db.query(
            Application.job_id,
            func.count(Application.id).label("total"),
            func.coalesce(func.sum(case((Application.status == ApplicationStatus.APPLIED, 1), else_=0)), 0).label("new"),
            func.coalesce(func.sum(case((Application.match_status == "pending", 1), else_=0)), 0).label("scoring"),
            func.coalesce(func.sum(case((Application.status == ApplicationStatus.SHORTLISTED, 1), else_=0)), 0).label("shortlisted"),
        )
        .filter(Application.job_id.in_(own_job_ids))
        .group_by(Application.job_id)
        .all()
    }
    job_status_counts = {
        _key(k): n
        for k, n in db.query(Job.status, func.count(Job.id))
        .filter(Job.created_by_id == user.id)
        .group_by(Job.status)
        .all()
    }
    jobs_total = sum(job_status_counts.values())
    jobs = (
        db.query(Job)
        .filter(Job.created_by_id == user.id)
        .order_by(Job.created_at.desc())
        .limit(100)
        .all()
    )

    def counts(job_id):
        row = per_job.get(job_id)
        if row is None:
            return 0, 0, 0, 0
        return int(row.total), int(row.new), int(row.scoring), int(row.shortlisted)

    job_rows = []
    for j in jobs:
        total, new, scoring, shortlisted = counts(j.id)
        job_rows.append({
            "id": str(j.id),
            "title": j.title,
            "status": _key(j.status),
            "applicant_count": total,
            "new_count": new,
            "still_scoring_count": scoring,
            "shortlisted_count": shortlisted,
        })

    # One grouped query for the hiring funnel across every owned job. Interview
    # is a sub-state of SHORTLISTED, so it is split out of the shortlisted bucket.
    funnel = {"applied": 0, "reviewing": 0, "shortlisted": 0, "interview": 0, "hired": 0, "rejected": 0}
    stage_rows = (
        db.query(Application.status, Application.shortlist_stage, func.count(Application.id))
        .filter(Application.job_id.in_(own_job_ids))
        .group_by(Application.status, Application.shortlist_stage)
        .all()
    )
    for status, stage, n in stage_rows:
        if status == ApplicationStatus.APPLIED:
            funnel["applied"] += n
        elif status == ApplicationStatus.UNDER_REVIEW:
            funnel["reviewing"] += n
        elif status == ApplicationStatus.SHORTLISTED:
            funnel["shortlisted"] += n
        elif status == ApplicationStatus.INTERVIEWING:
            funnel["interview"] += n
        elif status == ApplicationStatus.HIRED:
            funnel["hired"] += n
        elif status == ApplicationStatus.REJECTED:
            funnel["rejected"] += n

    interview_filter = (
        Job.created_by_id == user.id,
        Application.interview_stage == InterviewStage.SCHEDULED,
        Application.interview_at >= now,
    )
    interviews_total = (
        db.query(func.count(Application.id)).join(Job, Job.id == Application.job_id).filter(*interview_filter).scalar()
    )
    interviews = (
        db.query(Application, Job.title)
        .join(Job, Job.id == Application.job_id)
        .filter(*interview_filter)
        .order_by(Application.interview_at.asc())
        .limit(20)
        .all()
    )
    return {
        "role": "recruiter",
        "jobs": job_rows,
        "jobs_total": jobs_total,
        "funnel": funnel,
        "quick_actions": {
            "draft_jobs": job_status_counts.get(JobStatus.DRAFT.value, 0),
            "published_jobs": job_status_counts.get(JobStatus.PUBLISHED.value, 0),
            "new_applicants": sum(int(r.new) for r in per_job.values()),
            "still_scoring": sum(int(r.scoring) for r in per_job.values()),
            "shortlisted": sum(int(r.shortlisted) for r in per_job.values()),
            "upcoming_interviews": interviews_total,
        },
        "upcoming_interviews": [
            {
                "application_id": str(a.id),
                "job_id": str(a.job_id),
                "job_title": title,
                "interview_at": a.interview_at,
            }
            for a, title in interviews
        ],
    }


def _admin_overview(db: Session, user: User) -> dict:
    """Admin / superuser dashboard.

    Requests and the audit feed are scoped: an admin only sees their own sub
    company's, the superuser sees everything. The system-health items (LLM
    configuration, queue depth, quota) are global on purpose and untouched.
    """
    is_superuser = user.role == UserRole.SUPERUSER
    pending_filter = [User.requested_role.isnot(None)]
    if not is_superuser:
        # An admin without a sub company matches nothing (default-deny).
        pending_filter.append(
            User.sub_company == user.sub_company if user.sub_company is not None else false()
        )
    pending = db.query(func.count(User.id)).filter(*pending_filter).scalar()
    unset_tasks = [
        t
        for (t,) in db.query(LLMConfig.task)
        .filter((LLMConfig.provider == "unset") | (LLMConfig.model == "unset"))
        .order_by(LLMConfig.task)
        .all()
    ]
    pending_users = (
        db.query(User)
        .filter(*pending_filter)
        .order_by(User.created_at.asc())
        .limit(5)
        .all()
    )
    depths = metrics.queue_depths()
    audit_query = db.query(AuditLog)
    if not is_superuser:
        audit_query = audit_query.filter(admin_scope(user))
    recent = audit_query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(10).all()
    return {
        "role": "admin",
        "is_superuser": is_superuser,
        "pending_recruiter_requests": pending,
        "pending_recruiters": [
            {
                "id": str(u.id), "email": u.email, "full_name": u.full_name, "created_at": u.created_at,
                "requested_role": _key(u.requested_role),
                "sub_company": _key(u.sub_company.value) if u.sub_company else None,
            }
            for u in pending_users
        ],
        "unset_llm_tasks": len(unset_tasks),
        "unset_llm_task_names": unset_tasks,
        "system_queue_depth": depths["total"] if depths else None,
        "quota_usage": metrics.quota_snapshot(),
        "recent_audit_activity": [
            {
                "id": str(a.id),
                "action": a.action,
                "resource_type": a.resource_type,
                "actor_email": a.actor_email,
                "created_at": a.created_at,
            }
            for a in recent
        ],
    }


@router.get("/overview")
def overview(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    if current_user.role == UserRole.USER:
        return _applicant_overview(db, current_user, now)
    if current_user.role == UserRole.RECRUITER:
        return _recruiter_overview(db, current_user, now)
    return _admin_overview(db, current_user)
