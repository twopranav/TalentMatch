"""Read access to the audit trail (written by app/core/audit.py: record_audit).

Who sees what:
  * superuser / admin: the complete audit trail, every resource type.
  * recruiter: only entries about their own jobs -- the job itself, and
    applications / application notes on those jobs. Never users, resumes, or
    anything about another recruiter's jobs.
  * everyone else: 403.
"""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.deps import require_recruiter_or_admin
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.job import Job
from app.models.user import User, UserRole
from app.models.resume import Resume
from app.schemas.audit import AuditLogRead

router = APIRouter()

# Audit rows that belong to a job via a job_id inside their JSON snapshot.
_JOB_SCOPED_TYPES = ("application", "application_note")

# Left out of the *response* (they stay in the database): match_details is a
# big JSON blob repeated in every application snapshot, which would make a
# page of history many times larger without telling anyone what changed.
_HEAVY_KEYS = {"match_details"}
# Changes on every write, so it would show up as a "change" in every row.
_NOISY_KEYS = {"updated_at"}


def _job_ref(model):
    """The job id (as text) stored in a row's snapshot. `after` is empty on a
    delete and `before` is empty on a create, so take whichever exists."""
    return func.coalesce(model.after["job_id"].astext, model.before["job_id"].astext)


def _recruiter_scope(user: User):
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
        func.coalesce(
            job_audit.after["created_by_id"].astext, job_audit.before["created_by_id"].astext
        ) == str(user.id),
    )

    def mine(job_id_text):
        return or_(job_id_text.in_(live_jobs), job_id_text.in_(ever_owned_jobs))

    return or_(
        # The job's own audit rows: its resource_id IS the job id.
        and_(AuditLog.resource_type == "job", mine(cast(AuditLog.resource_id, String))),
        # Applications / notes: the job id is inside the snapshot.
        and_(AuditLog.resource_type.in_(_JOB_SCOPED_TYPES), mine(_job_ref(AuditLog))),
    )


def _strip_heavy(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(snapshot, dict):
        return None
    return {k: v for k, v in snapshot.items() if k not in _HEAVY_KEYS}


def _changed_fields(before: Any, after: Any) -> list[str]:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []  # create / delete: there is nothing to compare against
    keys = (before.keys() | after.keys()) - _NOISY_KEYS
    return sorted(k for k in keys if before.get(k) != after.get(k))


def _to_read(row: AuditLog, resource_label: str | None = None) -> AuditLogRead:
    return AuditLogRead(
        id=row.id, actor_id=row.actor_id, actor_email=row.actor_email,
        action=row.action, resource_type=row.resource_type, resource_id=row.resource_id, resource_label=resource_label,
        before=_strip_heavy(row.before), after=_strip_heavy(row.after),
        changed_fields=_changed_fields(row.before, row.after),
        created_at=row.created_at,
    )


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    response: Response,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    resource_type: str | None = Query(default=None, max_length=50, description="job | user | application | application_note | resume"),
    resource_id: uuid.UUID | None = Query(default=None, description="History of one specific record"),
    job_id: uuid.UUID | None = Query(default=None, description="Everything about one job: the job, its applications and their notes"),
    action: str | None = Query(default=None, max_length=50, description="create | update | delete"),
    actor_id: uuid.UUID | None = Query(default=None, description="Only entries made by this user"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    """Audit entries, newest first. The size of the whole filtered set comes
    back in the X-Total-Count header so the client can draw page numbers.
    Filters combine with AND, and always on top of the caller's role scope."""
    filters = []
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPERUSER):
        # Default-deny shape: anyone who got past the dependency but isn't an
        # admin/superuser is scoped, rather than the reverse.
        filters.append(_recruiter_scope(current_user))
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)
    if resource_id:
        filters.append(AuditLog.resource_id == resource_id)
    if action:
        filters.append(AuditLog.action == action)
    if actor_id:
        filters.append(AuditLog.actor_id == actor_id)
    if job_id:
        jid = str(job_id)
        filters.append(or_(
            and_(AuditLog.resource_type == "job", cast(AuditLog.resource_id, String) == jid),
            and_(AuditLog.resource_type.in_(_JOB_SCOPED_TYPES), _job_ref(AuditLog) == jid),
        ))

    total = db.query(func.count(AuditLog.id)).filter(*filters).scalar()
    response.headers["X-Total-Count"] = str(total)

    rows = (
        db.query(AuditLog)
        .filter(*filters)
        # id as the tie-break so paging never repeats or skips a row when
        # several entries share a timestamp.
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    # Resolve labels in at most one query per resource type for this page.
    ids = {kind: {r.resource_id for r in rows if r.resource_type == kind} for kind in ("job", "user", "resume")}
    # Application and note labels are the parent job title, derived from snapshots.
    for r in rows:
        if r.resource_type in ("application", "application_note"):
            raw = (r.after or {}).get("job_id") or (r.before or {}).get("job_id")
            if raw:
                try: ids["job"].add(uuid.UUID(str(raw)))
                except (ValueError, TypeError): pass
    labels: dict[tuple[str, uuid.UUID], str] = {}
    if ids["job"]:
        labels.update({("job", x.id): x.title for x in db.query(Job.id, Job.title).filter(Job.id.in_(ids["job"])).all()})
    if ids["user"]:
        labels.update({("user", x.id): x.email for x in db.query(User.id, User.email).filter(User.id.in_(ids["user"])).all()})
    if ids["resume"]:
        labels.update({("resume", x.id): x.original_filename for x in db.query(Resume.id, Resume.original_filename).filter(Resume.id.in_(ids["resume"])).all()})
    output = []
    for r in rows:
        key_type = r.resource_type
        key_id = r.resource_id
        if key_type in ("application", "application_note"):
            raw = (r.after or {}).get("job_id") or (r.before or {}).get("job_id")
            try: key_type, key_id = "job", uuid.UUID(str(raw))
            except (ValueError, TypeError): key_type, key_id = r.resource_type, r.resource_id
        label = labels.get((key_type, key_id))
        if label is None:
            snap = r.before or r.after or {}
            label = snap.get({"job":"title", "user":"email", "resume":"original_filename", "application":"job_id", "application_note":"job_id"}.get(r.resource_type, ""))
        output.append(_to_read(r, str(label) if label is not None else None))
    return output
