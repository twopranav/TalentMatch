import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from app.core.audit import record_audit, snapshot
from app.core.deps import get_current_user, require_recruiter_or_admin
from app.db.session import get_db
from app.models.application import Application
from app.models.job import Job, JobStatus
from app.models.user import User, UserRole
from app.schemas.application import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationStatusUpdate,
    ApplicationWithJob,
    ApplicationWithApplicant,
)

router = APIRouter()

@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def apply_to_job(
    payload: ApplicationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.get(Job, payload.job_id)
    if job is None or job.status != JobStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    existing = (
        db.query(Application)
        .filter(Application.user_id == current_user.id, Application.job_id == job.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You have already applied to this job")

    application = Application(user_id=current_user.id, job_id=job.id)
    db.add(application)
    db.flush()  # assigns application.id before we snapshot it for the audit row
    record_audit(
        db, actor=current_user, action="create", resource_type="application",
        resource_id=application.id, after=snapshot(application, "application"),
    )
    db.commit()
    db.refresh(application)
    return application

@router.get("/me", response_model=list[ApplicationWithJob])
def list_my_applications(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    apps = (
        db.query(Application)
        .options(joinedload(Application.job))
        .filter(Application.user_id == current_user.id)
        .order_by(Application.applied_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        ApplicationWithJob(
            id=a.id, user_id=a.user_id, job_id=a.job_id, status=a.status,
            applied_at=a.applied_at, updated_at=a.updated_at,
            job_title=a.job.title, job_status=a.job.status.value,
        )
        for a in apps
    ]

def _assert_can_view_job_applications(job: Job, current_user: User):
    is_privileged = current_user.role in (UserRole.ADMIN, UserRole.SUPERUSER)
    if not is_privileged and job.created_by_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to view these applications")

@router.get("/job/{job_id}", response_model=list[ApplicationWithApplicant])
def list_job_applications(
    job_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    _assert_can_view_job_applications(job, current_user)

    apps = (
        db.query(Application)
        .options(joinedload(Application.user))
        .filter(Application.job_id == job_id)
        .order_by(Application.applied_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        ApplicationWithApplicant(
            id=a.id, user_id=a.user_id, job_id=a.job_id, status=a.status,
            applied_at=a.applied_at, updated_at=a.updated_at,
            applicant_email=a.user.email, applicant_name=a.user.full_name,
        )
        for a in apps
    ]

@router.patch("/{application_id}/status", response_model=ApplicationRead)
def update_application_status(
    application_id: uuid.UUID,
    payload: ApplicationStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_recruiter_or_admin),
):
    application = db.get(Application, application_id)
    if application is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    _assert_can_view_job_applications(application.job, current_user)
    before = snapshot(application, "application")
    application.status = payload.status
    record_audit(
        db, actor=current_user, action="update", resource_type="application",
        resource_id=application.id, before=before, after=snapshot(application, "application"),
    )
    db.commit()
    db.refresh(application)
    return application

@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def withdraw_application(
    application_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    application = db.get(Application, application_id)
    if application is None or application.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    record_audit(
        db, actor=current_user, action="delete", resource_type="application",
        resource_id=application.id, before=snapshot(application, "application"),
    )
    db.delete(application)
    db.commit()