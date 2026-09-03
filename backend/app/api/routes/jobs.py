import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, require_recruiter_or_admin
from app.core.jd_extract import extract_text_from_upload
from app.db.session import get_db
from app.models.job import Job, JobStatus, EmploymentType, SeniorityLevel, RemoteType
from app.models.user import User, UserRole
from app.schemas.job import JobCreate, JobRead, JobUpdate
from datetime import datetime, timezone

router = APIRouter()

@router.get("", response_model=list[JobRead])
def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    location: str | None = Query(default=None),
    employment_type: EmploymentType | None = Query(default=None),
    seniority: SeniorityLevel | None = Query(default=None),
    remote_type: RemoteType | None = Query(default=None),
    department: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Job)

    if current_user.role == UserRole.USER:
        query = query.filter(Job.status == JobStatus.PUBLISHED)
    elif status_filter is not None:
        query = query.filter(Job.status == status_filter)

    if location:
        query = query.filter(Job.location.ilike(f"%{location}%"))
    if employment_type:
        query = query.filter(Job.employment_type == employment_type)
    if seniority:
        query = query.filter(Job.seniority == seniority)
    if remote_type:
        query = query.filter(Job.remote_type == remote_type)
    if department:
        query = query.filter(Job.department.ilike(f"%{department}%"))

    return query.all()

@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    job = Job(title=payload.title, description=payload.description, created_by=current_user)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

def _get_visible_job(job_id: uuid.UUID, db: Session, current_user: User) -> Job:
    """Read-access lookup: USERs can see any PUBLISHED job; recruiters/
    admins/superuser can see any job at all (full view, no ownership restriction)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    if current_user.role == UserRole.USER and job.status != JobStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job

def _get_owned_job(job_id: uuid.UUID, db: Session, current_user: User) -> Job:
    """Write-access lookup: admins/superuser can mutate any job; recruiters
    only their own. Same 404-for-both trick as before to avoid leaking
    existence of jobs the caller doesn't own."""
    job = db.get(Job, job_id)
    is_privileged = current_user.role in (UserRole.ADMIN, UserRole.SUPERUSER)
    if job is None or (not is_privileged and job.created_by_id != current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job

@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _get_visible_job(job_id, db, current_user)

@router.patch("/{job_id}", response_model=JobRead)
def update_job(job_id: uuid.UUID, payload: JobUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    job = _get_owned_job(job_id, db, current_user)
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("status") == JobStatus.PUBLISHED and job.published_at is None:
        job.published_at = datetime.now(timezone.utc)
    for field, value in updates.items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return job

@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    job = _get_owned_job(job_id, db, current_user)
    db.delete(job)
    db.commit()

@router.post("/{job_id}/jd", response_model=JobRead)
async def upload_jd(job_id: uuid.UUID, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    job = _get_owned_job(job_id, db, current_user)
    job.jd_raw_text = await extract_text_from_upload(file)
    db.commit()
    db.refresh(job)
    return job