import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from app.core.deps import get_current_user, require_recruiter_or_admin
from app.core.jd_extract import extract_text_from_upload
from app.db.session import get_db
from app.models.job import Job
from app.models.user import User, UserRole
from app.schemas.job import JobCreate, JobRead, JobUpdate

router = APIRouter()

@router.get("", response_model=list[JobRead])
def list_jobs(db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    query = db.query(Job)
    if current_user.role != UserRole.ADMIN:
        query = query.filter(Job.created_by_id == current_user.id)
    return query.all()

@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreate, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    job = Job(title=payload.title, description=payload.description, created_by=current_user)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job

def _get_owned_job(job_id: uuid.UUID, db: Session, current_user: User) -> Job:
    """Shared lookup so GET/PATCH/DELETE all enforce the same ownership rule
    the same way — one place to fix if that rule ever changes."""
    job = db.get(Job, job_id)
    if current_user.role != UserRole.ADMIN and job.created_by_id != current_user.id:
        # same 404 for "doesn't exist" and "exists but isn't yours" — deliberately;
        # a 403 here would confirm to an attacker that the id is valid.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job

@router.get("/{job_id}", response_model=JobRead)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    return _get_owned_job(job_id, db, current_user)

@router.patch("/{job_id}", response_model=JobRead)
def update_job(job_id: uuid.UUID, payload: JobUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_recruiter_or_admin)):
    job = _get_owned_job(job_id, db, current_user)
    for field, value in payload.model_dump(exclude_unset=True).items():
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